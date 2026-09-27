from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import ScenarioVariant, SimulationJob
from app.database.repositories.scenarios import ScenarioRepository
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.database.repositories.projects import ProjectRepository
from app.modelling.base import ExecutionResult, ModelAdapter, PreparedModel
from app.modelling.schemas import ModelPrepareRequest
from app.orchestration.manager import SimulationJobManager
from app.schemas.scenarios import ScenarioConfig, SimulationModel
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
from app.scenarios.generator import generate_scenario_variants


def valid_base() -> ScenarioConfig:
    return ScenarioConfig(
        name="Job Scenario",
        initial_reservoir_water_level_m=120,
        reservoir_volume_m3=5_000_000,
        breach_width_m=40,
        breach_depth_m=20,
        breach_formation_time_s=300,
        initial_discharge_m3s=200,
        simulation_duration_s=3600,
        model=SimulationModel.SPH,
    )


class FakeAdapter(ModelAdapter):
    model = SimulationModel.SPH
    adapter_version = "fake-phase7"
    supports_native_result_processing = False

    def __init__(self, mode="success"):
        self.mode = mode

    def prepare(self, *, variant_parameters, native_input_directory, working_directory, preprocessing_artifacts=None):
        working_directory.mkdir(parents=True, exist_ok=True)
        manifest = working_directory / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        return PreparedModel(
            model=self.model,
            adapter_version=self.adapter_version,
            working_directory=working_directory,
            manifest_path=manifest,
            command=[sys.executable, "fake-solver"],
            execution_steps=[[sys.executable, "fake-solver"]],
        )

    def execute(self, prepared, *, timeout_s, progress_callback=None, cancel_check=None):
        if progress_callback:
            progress_callback(25, "step_1_running")
        time.sleep(0.5 if self.mode == "slow" else 0.05)
        if cancel_check and cancel_check():
            return ExecutionResult(
                model=self.model, status="cancelled", exit_code=-2, duration_s=0.05,
                working_directory=prepared.working_directory, command=prepared.command,
                stdout_log=prepared.working_directory / "stdout.log",
                stderr_log=prepared.working_directory / "stderr.log",
            )
        if self.mode == "fail":
            return ExecutionResult(
                model=self.model, status="failed", exit_code=7, duration_s=0.05,
                working_directory=prepared.working_directory, command=prepared.command,
                stdout_log=prepared.working_directory / "stdout.log",
                stderr_log=prepared.working_directory / "stderr.log",
            )
        if progress_callback:
            progress_callback(90, "execution_finished")
        return ExecutionResult(
            model=self.model, status="completed", exit_code=0, duration_s=0.05,
            working_directory=prepared.working_directory, command=prepared.command,
            stdout_log=prepared.working_directory / "stdout.log",
            stderr_log=prepared.working_directory / "stderr.log",
            summary={"max_velocity_mps": 5.0},
        )

    def parse_result(self, working_directory):
        return None, [], []


class FakeModellingService:
    def __init__(self, mode="success"):
        self.mode = mode
        self.adapter = FakeAdapter(mode)

    def prepare_variant(self, db, *, project_id, scenario_id, variant_id, model, config):
        native = Path(config.native_input_directory)
        work = Path(config.working_directory or (Path("data/model_runs") / variant_id / model.value))
        prepared = self.adapter.prepare(
            variant_parameters=ScenarioVariantRepository().get(db, variant_id).parameters,
            native_input_directory=native,
            working_directory=work,
        )
        from app.modelling.schemas import ModelPrepareResponse
        return ModelPrepareResponse(
            model=prepared.model,
            adapter_version=prepared.adapter_version,
            working_directory=str(prepared.working_directory),
            manifest_path=str(prepared.manifest_path),
            command=prepared.command,
            execution_steps=prepared.execution_steps,
            native_input_directory=str(native.resolve()),
            warnings=[],
        )

    def _adapter(self, model, config):
        return self.adapter


def setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    project = ProjectRepository().create(db, name="Phase 7 Project")
    scenario = ScenarioRepository().create(db, project_id=project.id, name=valid_base().name, model="sph", config=valid_base().model_dump(mode="json"))
    variant = generate_scenario_variants(valid_base(), ScenarioGenerationConfig(presets=[ScenarioPreset.MAJOR_BREACH]))[0]
    persisted = ScenarioVariantRepository().create(
        db,
        base_scenario_id=scenario.id,
        code=variant.code,
        kind=variant.kind,
        preset=variant.preset,
        breach_fraction=variant.breach_fraction,
        model=variant.model.value,
        parameters=variant.parameters,
        assumptions=variant.assumptions,
    )
    db.close()
    return engine, SessionLocal, project.id, scenario.id, persisted.id


def wait_for_status(SessionLocal, job_id, target={"completed", "failed", "cancelled"}, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        db = SessionLocal()
        try:
            job = db.get(SimulationJob, job_id)
            if job and job.status in target:
                return job
        finally:
            db.close()
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal state")


def test_success_job_persists_progress_and_result(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("success")
    native = tmp_path / "native"
    native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "work"), timeout_s=10)
    db = SessionLocal()
    try:
        job = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=1)
        assert job.status == "queued"
    finally:
        db.close()
    done = wait_for_status(SessionLocal, job.id)
    assert done.status == "completed"
    assert done.progress == 100.0
    assert done.attempt == 1
    assert done.result["summary"]["max_velocity_mps"] == 5.0
    manager.shutdown(wait=True)
    engine.dispose()


def test_retry_on_failed_attempt(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("fail")
    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "work"), timeout_s=10)
    db = SessionLocal(); job = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=2); db.close()
    done = wait_for_status(SessionLocal, job.id)
    assert done.status == "failed"
    assert done.attempt == 2
    assert "exit code 7" in done.error_message
    manager.shutdown(wait=True); engine.dispose()


def test_cancel_queued_job_before_worker_starts(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("slow")
    native = tmp_path / "native"; native.mkdir()
    first_request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "work1"), timeout_s=10)
    second_request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "work2"), timeout_s=10)
    db = SessionLocal()
    first = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=first_request, max_attempts=1)
    second = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=second_request, max_attempts=1)
    db.close()
    cancel_db = SessionLocal(); cancelled = manager.cancel(cancel_db, second.id); cancel_db.close()
    final_second = wait_for_status(SessionLocal, second.id)
    final_first = wait_for_status(SessionLocal, first.id)
    assert cancelled.status == "cancelled"
    assert final_second.status == "cancelled"
    assert final_first.status == "completed"
    manager.shutdown(wait=True); engine.dispose()


def test_recover_interrupted_job_moves_it_back_to_queue(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    from app.database.repositories.simulation_jobs import SimulationJobRepository
    from datetime import datetime, timezone
    db = SessionLocal()
    job = SimulationJobRepository().create(
        db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model="sph",
        status="running", progress=55.0, current_step="step_2_running", attempt=1, max_attempts=2,
        timeout_s=10, config={}, cancel_requested=False, started_at=datetime.now(timezone.utc)
    )
    repo = SimulationJobRepository()
    recovered = repo.recover_interrupted(db)
    refreshed = repo.get(db, job.id)
    db.close()
    assert recovered == 1
    assert refreshed.status == "queued"
    assert refreshed.progress == 0.0
    assert refreshed.cancel_requested is False
    engine.dispose()


def test_cancel_running_job_sets_terminal_cancelled(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("slow")
    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "running"), timeout_s=10)
    db = SessionLocal(); job = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=1); db.close()
    deadline = time.time() + 3
    while time.time() < deadline:
        db = SessionLocal(); state = db.get(SimulationJob, job.id); db.close()
        if state and state.status in {"running", "preparing"}:
            break
        time.sleep(0.02)
    cancel_db = SessionLocal(); requested = manager.cancel(cancel_db, job.id); cancel_db.close()
    final = wait_for_status(SessionLocal, job.id)
    assert requested.status == "cancel_requested"
    assert final.status == "cancelled"
    assert final.cancel_requested is True
    manager.shutdown(wait=True); engine.dispose()


def test_manager_applies_cpu_fallback_before_solver_execution(tmp_path):
    from app.modelling.runtime import SolverRuntime
    from app.modelling.schemas import SphExecutionDevice

    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    fake = FakeModellingService("success")
    seen = {}
    fake.runtime_status = lambda: {
        "sph": SolverRuntime(
            "sph", True, True, "5.4.3", "gpu", "cpu", None,
            {"gencase": "/g", "gpu": "/gpu", "cpu": "/cpu", "partvtk": "/p"},
            {"available": False, "count": 0, "devices": [], "source": None},
            ["CPU fallback"],
        ),
        "delft3d": SolverRuntime(
            "delft3d", False, False, None, None, None, None,
            {"dimr": None, "dflowfm": None, "runner": None},
            {"available": False, "count": 0, "devices": [], "source": None},
            ["unavailable"],
        ),
    }
    original_adapter = fake._adapter

    def tracked_adapter(model, config):
        seen["sph_device"] = getattr(config.sph_device, "value", config.sph_device)
        return original_adapter(model, config)

    fake._adapter = tracked_adapter
    manager.modelling = fake
    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(
        native_input_directory=str(native), working_directory=str(tmp_path / "work"),
        timeout_s=10, sph_device=SphExecutionDevice.GPU,
    )
    db = SessionLocal()
    try:
        job = manager.create_and_submit(
            db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id,
            model=SimulationModel.SPH, prepare=request, max_attempts=1,
        )
    finally:
        db.close()
    done = wait_for_status(SessionLocal, job.id)
    assert done.status == "completed"
    assert seen["sph_device"] == "cpu"
    manager.shutdown(wait=True)
    engine.dispose()


def test_job_attempts_get_isolated_working_directories(tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    seen = []

    class CaptureModelling(FakeModellingService):
        def prepare_variant(self, db, *, project_id, scenario_id, variant_id, model, config):
            seen.append(config.working_directory)
            return super().prepare_variant(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=model, config=config)

        def runtime_status(self):
            return {"sph": type("Runtime", (), {"ready": True, "effective_device": "cpu", "runner_mode": None, "binaries": {}})(), "delft3d": type("Runtime", (), {"ready": False})()}

    manager.modelling = CaptureModelling("success")
    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), timeout_s=10)
    db = SessionLocal()
    first = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=1)
    second = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=1)
    db.close()
    wait_for_status(SessionLocal, first.id); wait_for_status(SessionLocal, second.id)
    manager.shutdown(wait=True); engine.dispose()
    assert len(seen) == 2 and seen[0] != seen[1]
    assert first.id in seen[0] and second.id in seen[1]


def test_completed_sph_job_runs_native_analysis_bridge(monkeypatch, tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("success")
    manager.modelling.adapter.supports_native_result_processing = True

    class FakeAnalysis:
        id = "analysis-bridge-test"
        analysis_version = "phase8-native-sph-v1"
        artifacts = {}

    calls = []

    def fake_analyze(self, db, job_id, *, flood_threshold_m=0.05, force=False):
        calls.append((job_id, flood_threshold_m))
        return FakeAnalysis()

    monkeypatch.setattr("app.services.analysis_service.AnalysisService.analyze_native_sph_job", fake_analyze)

    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "bridge"), timeout_s=10)
    db = SessionLocal()
    job = manager.create_and_submit(
        db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id,
        model=SimulationModel.SPH, prepare=request, max_attempts=1,
    )
    db.close()
    final = wait_for_status(SessionLocal, job.id)
    assert final.status == "completed"
    assert final.result["analysis_result_id"] == "analysis-bridge-test"
    assert final.result["native_analysis"]["status"] == "completed"
    assert calls == [(job.id, 0.05)]
    manager.shutdown(wait=True); engine.dispose()


def test_reconcile_completed_native_jobs_attaches_analysis_without_rerun(monkeypatch, tmp_path):
    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("success")
    class FakeAnalysis:
        id = "analysis-reconcile-test"
        analysis_version = "phase8-native-sph-v1"
        artifacts = {"flood_extent_geojson": "/tmp/flood.geojson"}
    calls = []
    def fake_analyze(self, db, job_id, *, flood_threshold_m=0.05, force=False):
        calls.append(job_id)
        return FakeAnalysis()
    monkeypatch.setattr("app.services.analysis_service.AnalysisService.analyze_native_sph_job", fake_analyze)
    native = tmp_path / "native"; native.mkdir()
    request = ModelPrepareRequest(native_input_directory=str(native), working_directory=str(tmp_path / "reconcile"), timeout_s=10)
    db = SessionLocal()
    job = manager.create_and_submit(db, project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=SimulationModel.SPH, prepare=request, max_attempts=1)
    db.close()
    final = wait_for_status(SessionLocal, job.id)
    assert final.status == "completed"
    # Remove the attached result to simulate an older completed job.
    db = SessionLocal(); stored = db.get(SimulationJob, job.id); stored.result = {}; db.commit(); db.close()
    assert manager.reconcile_completed_native_results(limit=8) == 1
    for _ in range(100):
        time.sleep(0.02)
        db = SessionLocal(); current = db.get(SimulationJob, job.id); db.close()
        if current.result and current.result.get("analysis_result_id") == "analysis-reconcile-test":
            break
    else:
        raise AssertionError("completed job was not reconciled")
    assert calls == [job.id]
    manager.shutdown(wait=True); engine.dispose()
