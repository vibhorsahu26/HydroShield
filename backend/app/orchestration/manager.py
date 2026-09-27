from __future__ import annotations

import signal

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.database.models import SimulationJob
from app.database.repositories.simulation_jobs import SimulationJobRepository
from app.database.repositories.projects import ProjectRepository
from app.database.repositories.scenarios import ScenarioRepository
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.modelling.schemas import ModelPrepareRequest
from app.modelling.service import ModellingService
from app.modelling.demo import generate_demo_case
from app.schemas.scenarios import SimulationModel
from app.schemas.analysis import ResultAnalysisRequest
from app.orchestration.states import JobStatus


class SimulationJobManager:
    """Durable job state in SQL plus a bounded in-process execution pool."""

    def __init__(self, *, session_factory: sessionmaker[Session], max_workers: int = 2):
        self.session_factory = session_factory
        self.jobs = SimulationJobRepository()
        self.projects = ProjectRepository()
        self.scenarios = ScenarioRepository()
        self.variants = ScenarioVariantRepository()
        self.modelling = ModellingService()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hydroshield-sim")
        self._futures: dict[str, Future] = {}
        self._lock = Lock()

    def shutdown(self, wait: bool = False) -> None:
        self.executor.shutdown(wait=wait, cancel_futures=True)

    def _session(self) -> Session:
        return self.session_factory()

    def create_and_submit(
        self,
        db: Session,
        *,
        project_id: str,
        scenario_id: str,
        variant_id: str,
        model: SimulationModel,
        prepare: ModelPrepareRequest,
        max_attempts: int,
    ) -> SimulationJob:
        project = self.projects.get(db, project_id)
        if project is None:
            raise ValueError("Project not found.")
        scenario = self.scenarios.get(db, scenario_id)
        if scenario is None or scenario.project_id != project_id:
            raise ValueError("Scenario not found for project.")
        variant = self.variants.get(db, variant_id)
        if variant is None or variant.base_scenario_id != scenario_id:
            raise ValueError("Scenario variant not found for scenario.")
        if variant.model not in {model.value, SimulationModel.BOTH.value}:
            raise ValueError(f"Variant model '{variant.model}' does not support '{model.value}'.")

        settings = get_settings()
        requested_mode = prepare.execution_mode.value if prepare.execution_mode is not None else None
        runtime_status = getattr(self.modelling, "runtime_status", None)
        runtime = None
        if callable(runtime_status):
            try:
                runtime = runtime_status().get(model.value)
            except Exception:
                runtime = None

        # An explicit native request must have the external runtime. For the normal
        # (unspecified) path, development/local deployments transparently fall back
        # to HydroShield's internal calculation when a native solver is unavailable.
        # Production remains strict unless the explicitly configured demo_mode is enabled.
        if requested_mode == "prototype":
            if not settings.demo_mode:
                raise RuntimeError("Internal fallback execution is disabled on this backend.")
        elif requested_mode == "native":
            if runtime is not None and not runtime.ready:
                raise RuntimeError(
                    "%s runtime is unavailable; simulation was not queued."
                    % ("DualSPHysics" if model == SimulationModel.SPH else "Delft3D FM")
                )
        elif runtime is not None and not runtime.ready and settings.environment.lower() == "production" and not settings.demo_mode:
            raise RuntimeError(
                "%s runtime is unavailable; simulation was not queued."
                % ("DualSPHysics" if model == SimulationModel.SPH else "Delft3D FM")
            )

        job = self.jobs.create(
            db,
            project_id=project_id,
            scenario_id=scenario_id,
            variant_id=variant_id,
            model=model.value,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            current_step="queued",
            attempt=0,
            max_attempts=max_attempts,
            timeout_s=prepare.timeout_s,
            config=prepare.model_dump(mode="json"),
            cancel_requested=False,
        )
        self.submit(job.id)
        return job

    def submit(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._futures and not self._futures[job_id].done():
                return
            future = self.executor.submit(self._run_job, job_id)
            self._futures[job_id] = future

    def recover_pending(self) -> int:
        db = self._session()
        try:
            if "simulation_jobs" not in inspect(db.bind).get_table_names():
                return 0
            self.jobs.recover_interrupted(db)
            rows = list(db.scalars(select(SimulationJob).where(SimulationJob.status == JobStatus.QUEUED.value)).all())
        finally:
            db.close()
        for job in rows:
            self.submit(job.id)
        return len(rows)

    def _update(self, job_id: str, **values) -> None:
        db = self._session()
        try:
            job = self.jobs.get(db, job_id)
            if job is not None:
                self.jobs.update(db, job, **values)
        finally:
            db.close()

    def _cancel_requested(self, job_id: str) -> bool:
        db = self._session()
        try:
            job = self.jobs.get(db, job_id)
            return bool(job and job.cancel_requested)
        finally:
            db.close()

    def cancel(self, db: Session, job_id: str) -> SimulationJob:
        job = self.jobs.get(db, job_id)
        if job is None:
            raise ValueError("Simulation job not found.")
        if job.status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            return job
        job = self.jobs.request_cancel(db, job)
        if job.status == JobStatus.QUEUED.value:
            self.jobs.update(db, job, status=JobStatus.CANCELLED.value, progress=0.0, current_step="cancelled_before_start", finished_at=datetime.now(timezone.utc))
        else:
            self.jobs.update(db, job, status=JobStatus.CANCEL_REQUESTED.value, current_step="cancellation_requested")
        return job

    def reconcile_completed_native_results(self, *, limit: int = 8) -> int:
        """Queue lightweight reconciliation for completed native jobs missing analysis.

        This repairs jobs created by older releases after an upgrade without forcing
        the user to manually open the Analysis page. Failures remain visible as
        postprocessing errors on the completed job rather than changing historical
        solver status.
        """
        db = self._session()
        try:
            if "simulation_jobs" not in inspect(db.bind).get_table_names():
                return 0
            rows = list(db.scalars(
                select(SimulationJob)
                .where(
                    SimulationJob.status == JobStatus.COMPLETED.value,
                    SimulationJob.model.in_([SimulationModel.SPH.value, SimulationModel.DELFT3D.value]),
                )
                .order_by(SimulationJob.created_at.desc())
                .limit(max(0, int(limit)))
            ).all())
        finally:
            db.close()
        candidates = [
            job for job in rows
            if not (job.result or {}).get("analysis_result_id") and job.working_directory
        ]
        for job in candidates:
            self.submit_native_reconciliation(job.id)
        return len(candidates)

    def submit_native_reconciliation(self, job_id: str) -> None:
        with self._lock:
            future_key = f"native-reconcile:{job_id}"
            if future_key in self._futures and not self._futures[future_key].done():
                return
            future = self.executor.submit(self._reconcile_completed_native_job, job_id)
            self._futures[future_key] = future

    def _reconcile_completed_native_job(self, job_id: str) -> None:
        db = self._session()
        try:
            job = self.jobs.get(db, job_id)
            if job is None or job.status != JobStatus.COMPLETED.value or (job.result or {}).get("analysis_result_id"):
                return
            model = SimulationModel(job.model)
            from app.services.analysis_service import AnalysisService
            analysis_service = AnalysisService()
            try:
                analyze_native = (
                    analysis_service.analyze_native_sph_job
                    if model == SimulationModel.SPH
                    else analysis_service.analyze_native_delft3d_job
                )
                analysis = analyze_native(db, job_id, flood_threshold_m=0.05)
                payload = dict(job.result or {})
                payload["analysis_result_id"] = analysis.id
                payload["postprocessing"] = {
                    "status": "completed",
                    "analysis_result_id": analysis.id,
                    "analysis_version": analysis.analysis_version,
                    "artifacts": analysis.artifacts,
                    "source": model.value,
                }
                payload["native_analysis"] = dict(payload["postprocessing"])
                self.jobs.update(db, job, result=payload, current_step="complete", progress=100.0)
            except Exception as exc:
                payload = dict(job.result or {})
                post = {"status": "failed", "error": str(exc), "source": model.value}
                payload["postprocessing"] = post
                payload["native_analysis"] = dict(post)
                warnings = list(payload.get("warnings") or [])
                warnings.append(f"Native {model.value} result reconciliation failed: {exc}")
                payload["warnings"] = warnings
                self.jobs.update(db, job, result=payload, current_step="complete", progress=100.0)
        finally:
            db.close()

    def _run_demo_job(
        self,
        job_id: str,
        *,
        project_id: str,
        scenario_id: str,
        variant_id: str,
        model: SimulationModel,
        config: ModelPrepareRequest,
        attempt: int,
    ) -> None:
        """Run the full browser-visible model lifecycle with deterministic fallback artifacts.

        The fallback reuses the normal result/analysis/export path for both supported
        hydrodynamic models when the requested native solver is unavailable.
        """
        settings = get_settings()
        if not settings.demo_mode and settings.environment.lower() == "production":
            raise RuntimeError("Internal fallback execution is disabled on this backend.")

        workdir = (
            Path(config.working_directory).resolve()
            if config.working_directory
            else settings.model_work_dir / "jobs" / job_id / f"attempt-{attempt}" / model.value
        )
        self._update(job_id, status=JobStatus.PREPARING.value, current_step="preparing_demo_inputs", progress=10.0)

        db = self._session()
        try:
            variant = self.variants.get(db, variant_id)
            variant_parameters = dict(variant.parameters or {}) if variant is not None else {}
        finally:
            db.close()

        self._update(job_id, status=JobStatus.RUNNING.value, current_step="running_solver", progress=25.0)
        demo = generate_demo_case(
            workdir,
            variant_parameters=variant_parameters,
            dem_raster=config.preprocessed_dem,
            river_vector=config.prepared_river,
            run_signature=f"{model.value}:{job_id}:{attempt}",
            model=model.value,
        )
        self._update(job_id, status=JobStatus.PROCESSING.value, current_step="processing_native_results", progress=75.0)

        config_payload = config.model_dump(mode="json")
        config_payload["working_directory"] = str(workdir)
        config_payload["preprocessed_dem"] = demo["dem_raster"]
        result_payload = {
            "status": "completed",
            "exit_code": 0,
            "duration_s": 1.2,
            "working_directory": demo["working_directory"],
            "stdout_log": None,
            "stderr_log": None,
            "artifacts": [
                demo["dem_raster"],
                demo["water_depth_raster"],
                demo["velocity_raster"],
                demo["arrival_time_raster"],
                demo["water_level_raster"],
                demo["discharge_csv"],
                *demo["time_series_water_depth"],
            ],
            "summary": demo["summary"],
            "warnings": [],
            "step_results": [
                {"index": 1, "status": "completed", "step": "prepare"},
                {"index": 2, "status": "completed", "step": "solve"},
                {"index": 3, "status": "completed", "step": "postprocess"},
            ],
        }

        db = self._session()
        try:
            job = self.jobs.get(db, job_id)
            if job is None:
                return
            self.jobs.update(
                db,
                job,
                config=config_payload,
                working_directory=demo["working_directory"],
                manifest_path=demo["manifest_path"],
                status=JobStatus.COMPLETED.value,
                current_step="complete",
                progress=90.0,
                result=result_payload,
                error_message=None,
            )
        finally:
            db.close()

        analysis_db = self._session()
        try:
            from app.services.analysis_service import AnalysisService

            analysis = AnalysisService().analyze_job(
                analysis_db,
                job_id,
                ResultAnalysisRequest(
                    water_depth_raster=demo["water_depth_raster"],
                    velocity_raster=demo["velocity_raster"],
                    arrival_time_raster=demo["arrival_time_raster"],
                    water_level_raster=demo["water_level_raster"],
                    dem_raster=demo["dem_raster"],
                    discharge_csv=demo["discharge_csv"],
                    flood_threshold_m=0.05,
                ),
            )
            job = self.jobs.get(analysis_db, job_id)
            if job is not None:
                payload = dict(job.result or {})
                payload["analysis_result_id"] = analysis.id
                payload["postprocessing"] = {
                    "status": "completed",
                    "analysis_result_id": analysis.id,
                    "analysis_version": analysis.analysis_version,
                    "artifacts": analysis.artifacts,
                }
                payload["native_analysis"] = dict(payload["postprocessing"])
                self.jobs.update(
                    analysis_db,
                    job,
                    status=JobStatus.COMPLETED.value,
                    current_step="complete",
                    progress=100.0,
                    result=payload,
                    finished_at=datetime.now(timezone.utc),
                    error_message=None,
                )
        except Exception as exc:
            job = self.jobs.get(analysis_db, job_id)
            if job is not None:
                payload = dict(job.result or {})
                payload["postprocessing"] = {"status": "failed", "error": str(exc)}
                payload["native_analysis"] = dict(payload["postprocessing"])
                self.jobs.update(
                    analysis_db,
                    job,
                    status=JobStatus.FAILED.value,
                    current_step="result_processing_failed",
                    progress=99.0,
                    result=payload,
                    finished_at=datetime.now(timezone.utc),
                    error_message=f"Prototype result processing failed: {exc}",
                )
                raise
        finally:
            analysis_db.close()

    def _native_runtime_is_ready(self, model: SimulationModel) -> bool:
        runtime_status = getattr(self.modelling, "runtime_status", None)
        if not callable(runtime_status):
            return False
        try:
            runtime = runtime_status()[model.value]
        except Exception:
            return False
        if not runtime.ready:
            return False
        binaries = runtime.binaries or {}
        # A concrete runtime detector returning ready is authoritative outside the
        # browser-only demo detector. In demo mode, the SPH detector may intentionally
        # report a synthetic ready state without binaries, so require real executables there.
        if not get_settings().demo_mode:
            return True
        if model == SimulationModel.SPH:
            return bool(binaries.get("gencase") and binaries.get("partvtk") and (binaries.get("gpu") or binaries.get("cpu")))
        return bool(binaries.get("runner"))

    def _run_job(self, job_id: str) -> None:
        for attempt in range(1, 10_000):
            db = self._session()
            try:
                job = self.jobs.get(db, job_id)
                if job is None:
                    return
                if job.status == JobStatus.CANCELLED.value:
                    return
                if job.attempt >= job.max_attempts:
                    return
                next_attempt = job.attempt + 1
                self.jobs.update(
                    db,
                    job,
                    attempt=next_attempt,
                    status=JobStatus.PREPARING.value,
                    current_step="preparing_inputs",
                    progress=5.0,
                    started_at=job.started_at or datetime.now(timezone.utc),
                    error_message=None,
                )
                job_attempt = next_attempt
                project_id, scenario_id, variant_id = job.project_id, job.scenario_id, job.variant_id
                model = SimulationModel(job.model)
                config = ModelPrepareRequest.model_validate(job.config)
                max_attempts = job.max_attempts
            finally:
                db.close()

            try:
                settings = get_settings()
                runtime_status = getattr(self.modelling, "runtime_status", None)
                runtime_known = callable(runtime_status)
                use_fallback = (
                    config.execution_mode is not None and config.execution_mode.value == "prototype"
                ) or (
                    config.execution_mode is None
                    and runtime_known
                    and (settings.demo_mode or settings.environment.lower() != "production")
                    and not self._native_runtime_is_ready(model)
                )
                if use_fallback:
                    self._run_demo_job(
                        job_id,
                        project_id=project_id,
                        scenario_id=scenario_id,
                        variant_id=variant_id,
                        config=config,
                        model=model,
                        attempt=job_attempt,
                    )
                    return
                self._update(job_id, status=JobStatus.PREPARING.value, current_step="preparing_inputs", progress=10.0)
                # Every queued job/attempt gets an isolated working directory.
                # Reusing variant/model directories lets concurrent workers overwrite
                # Case_Def.xml, bathymetry, and DualSPHysics output files, which can
                # corrupt a native run (especially with two GPU jobs sharing one GPU).
                effective_job_config = config.model_copy(deep=True)
                if not effective_job_config.working_directory:
                    job_workdir = (
                        get_settings().model_work_dir
                        / "jobs"
                        / job_id
                        / f"attempt-{next_attempt}"
                        / model.value
                    )
                    effective_job_config.working_directory = str(job_workdir)
                db = self._session()
                try:
                    prepared = self.modelling.prepare_variant(
                        db,
                        project_id=project_id,
                        scenario_id=scenario_id,
                        variant_id=variant_id,
                        model=model,
                        config=effective_job_config,
                    )
                finally:
                    db.close()
                self._update(
                    job_id,
                    working_directory=prepared.working_directory,
                    manifest_path=prepared.manifest_path,
                    status=JobStatus.RUNNING.value,
                    current_step="running_solver",
                    progress=15.0,
                )

                # Runtimes can disappear between queueing and execution. Re-check
                # immediately before launching the external process so a missing
                # solver produces a clear lifecycle failure instead of a low-level
                # FileNotFoundError. Test doubles without runtime_status retain the
                # historical behavior.
                runtime_status = getattr(self.modelling, "runtime_status", None)
                runtime = None
                if callable(runtime_status):
                    runtime = runtime_status()[model.value]
                    if not runtime.ready:
                        raise RuntimeError(
                            "%s runtime became unavailable before execution."
                            % ("DualSPHysics" if model == SimulationModel.SPH else "Delft3D FM")
                        )

                # Rebuild the adapter through the same modelling service so the job
                # uses the exact Phase 6 configuration contract. Apply the fresh
                # runtime-selected fallback here as well; otherwise a GPU request
                # could be prepared as CPU fallback but executed with the unavailable
                # GPU binary, or Delft3D could switch runners during preparation and
                # then switch back during execution.
                effective_config = config.model_copy(deep=True)
                runtime_status = getattr(self.modelling, "runtime_status", None)
                if callable(runtime_status):
                    runtime = runtime_status()[model.value]
                    if model == SimulationModel.SPH:
                        from app.modelling.schemas import SphExecutionDevice
                        if runtime.effective_device:
                            effective_config.sph_device = SphExecutionDevice(runtime.effective_device)
                    elif model == SimulationModel.DELFT3D:
                        from app.modelling.schemas import Delft3DRunnerMode
                        if runtime.runner_mode:
                            effective_config.delft3d_runner_mode = Delft3DRunnerMode(runtime.runner_mode)
                        runner = runtime.binaries.get("runner")
                        if runner:
                            effective_config.solver_executable = str(runner)
                adapter = self.modelling._adapter(model, effective_config)
                from app.modelling.base import PreparedModel
                prepared_model = PreparedModel(
                    model=prepared.model,
                    adapter_version=prepared.adapter_version,
                    working_directory=Path(prepared.working_directory),
                    manifest_path=Path(prepared.manifest_path),
                    command=prepared.command,
                    execution_steps=prepared.execution_steps,
                    warnings=prepared.warnings,
                )

                def progress(pct: float, step: str) -> None:
                    self._update(job_id, progress=min(99.0, max(15.0, pct)), current_step=step)

                result = adapter.execute(
                    prepared_model,
                    timeout_s=config.timeout_s,
                    progress_callback=progress,
                    cancel_check=lambda: self._cancel_requested(job_id),
                )
                self._update(job_id, status=JobStatus.PROCESSING.value, current_step="persisting_results", progress=98.0)
                result_payload = {
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "duration_s": result.duration_s,
                    "working_directory": str(result.working_directory),
                    "stdout_log": str(result.stdout_log),
                    "stderr_log": str(result.stderr_log),
                    "artifacts": [str(p) for p in result.artifacts],
                    "summary": result.summary,
                    "warnings": list(result.warnings),
                    "step_results": result.step_results,
                }

                final_status = result.status
                if final_status == "completed":
                    # HydroShield's simulation contract does not end at native solver
                    # exit. A job becomes fully completed only after its native result
                    # has been normalized into Phase 8 analysis artifacts. This makes
                    # the persisted state truthful: a solver can finish successfully
                    # while the HydroShield result pipeline still fails.
                    if model in {SimulationModel.SPH, SimulationModel.DELFT3D} and getattr(adapter, "supports_native_result_processing", False):
                        self._update(
                            job_id,
                            status=JobStatus.PROCESSING.value,
                            current_step="processing_native_results",
                            progress=99.0,
                        )
                        try:
                            from app.services.analysis_service import AnalysisService

                            analysis_db = self._session()
                            try:
                                analysis_service = AnalysisService()
                                analyze_native = (
                                    analysis_service.analyze_native_sph_job
                                    if model == SimulationModel.SPH
                                    else analysis_service.analyze_native_delft3d_job
                                )
                                analysis = analyze_native(
                                    analysis_db,
                                    job_id,
                                    flood_threshold_m=0.05,
                                )
                            finally:
                                analysis_db.close()
                            result_payload["analysis_result_id"] = analysis.id
                            result_payload["postprocessing"] = {
                                "status": "completed",
                                "analysis_result_id": analysis.id,
                                "analysis_version": analysis.analysis_version,
                                "artifacts": analysis.artifacts,
                            }
                            # Keep the explicit native-analysis key used by the
                            # dashboard/reconciliation contract while postprocessing
                            # remains the canonical lifecycle field.
                            result_payload["native_analysis"] = dict(result_payload["postprocessing"])
                        except Exception as analysis_exc:
                            result_payload["postprocessing"] = {
                                "status": "failed",
                                "error": str(analysis_exc),
                            }
                            result_payload["native_analysis"] = dict(result_payload["postprocessing"])
                            result_payload["warnings"].append(
                                f"Native {model.value} result processing failed: {analysis_exc}"
                            )
                            self._update(
                                job_id,
                                status=JobStatus.FAILED.value,
                                current_step="result_processing_failed",
                                progress=99.0,
                                result=result_payload,
                                finished_at=datetime.now(timezone.utc),
                                error_message=(
                                    f"{model.value.upper()} solver completed, but HydroShield result processing failed: "
                                    f"{analysis_exc}"
                                ),
                            )
                            return

                    self._update(
                        job_id,
                        status=JobStatus.COMPLETED.value,
                        current_step="complete",
                        progress=100.0,
                        result=result_payload,
                        finished_at=datetime.now(timezone.utc),
                        error_message=None,
                    )
                    return
                if final_status == "cancelled":
                    self._update(job_id, status=JobStatus.CANCELLED.value, current_step="cancelled", progress=95.0, result=result_payload, finished_at=datetime.now(timezone.utc), error_message="Cancellation requested by user.")
                    return

                error = f"Model execution ended with status '{final_status}' and exit code {result.exit_code}."
                if result.step_results:
                    failed_step = next((step for step in reversed(result.step_results) if step.get("status") == "failed"), None)
                    if failed_step is not None:
                        error += f" Failed pipeline step {failed_step.get('index')}."
                if result.exit_code < 0:
                    try:
                        signal_name = signal.Signals(-result.exit_code).name
                    except ValueError:
                        signal_name = f"SIG{-result.exit_code}"
                    error += f" Process terminated by signal {-result.exit_code} ({signal_name})."
                if job_attempt < max_attempts:
                    self._update(job_id, status=JobStatus.RETRYING.value, current_step="retrying", progress=0.0, result=result_payload, error_message=error)
                    self._update(job_id, status=JobStatus.QUEUED.value, current_step="queued_for_retry", progress=0.0)
                    continue
                self._update(job_id, status=JobStatus.FAILED.value, current_step="failed", progress=95.0, result=result_payload, finished_at=datetime.now(timezone.utc), error_message=error)
                return
            except Exception as exc:
                error = f"Simulation job failed before completion: {exc}"
                if job_attempt < max_attempts:
                    self._update(job_id, status=JobStatus.RETRYING.value, current_step="retrying", progress=0.0, error_message=error)
                    self._update(job_id, status=JobStatus.QUEUED.value, current_step="queued_for_retry", progress=0.0)
                    continue
                self._update(job_id, status=JobStatus.FAILED.value, current_step="failed", progress=95.0, finished_at=datetime.now(timezone.utc), error_message=error)
                return

    def get(self, db: Session, job_id: str) -> SimulationJob | None:
        return self.jobs.get(db, job_id)

    def list_for_project(self, db: Session, project_id: str) -> list[SimulationJob]:
        return self.jobs.list_for_project(db, project_id)
