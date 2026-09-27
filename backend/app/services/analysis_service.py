from __future__ import annotations

from pathlib import Path
import json
from sqlalchemy.orm import Session

from app.analysis.comparison import compare_analysis_artifacts
from app.analysis.exposure import complete_demo_exposure
from app.analysis.result_processor import process_result
from app.database.models import SimulationJob
from app.database.repositories.analysis import AnalysisResultRepository, ResultComparisonRepository
from app.database.repositories.datasets import DatasetRepository
from app.orchestration.states import JobStatus
from app.modelling.sph.result_to_rasters import build_sph_analysis_rasters
from app.modelling.delft3d.result_to_rasters import build_delft3d_analysis_rasters
from app.schemas.analysis import ComparisonType, ResultAnalysisRequest, ResultComparisonRequest
from app.core.errors import NotFoundError, ConflictError
from app.core.config import get_settings

ANALYSIS_VERSION = "phase8-v1"


class AnalysisService:
    def __init__(self):
        self.results = AnalysisResultRepository()
        self.comparisons = ResultComparisonRepository()

    def _job(self, db: Session, job_id: str) -> SimulationJob:
        job = db.get(SimulationJob, job_id)
        if job is None:
            raise NotFoundError("Simulation job not found.")
        if job.status != JobStatus.COMPLETED.value:
            raise ConflictError(f"Simulation job must be completed before analysis; current status is '{job.status}'.")
        return job

    def _native_sph_dem_path(self, job: SimulationJob) -> Path:
        prepare = job.config or {}
        value = prepare.get("preprocessed_dem")
        if not value:
            raise ConflictError(
                "The completed SPH job has no persisted preprocessed DEM path; native result rasterisation cannot be performed."
            )
        path = Path(value).resolve()
        if not path.is_file():
            raise ConflictError(f"The persisted preprocessed DEM is not available: {path}")
        return path

    def _native_exposure_layers(self, db: Session, project_id: str) -> dict[str, str]:
        datasets = DatasetRepository().list_for_project(db, project_id)
        layers: dict[str, str] = {}
        for dataset in datasets:
            path = Path(dataset.storage_uri)
            if not path.is_file():
                continue
            logical_type = (dataset.source_metadata or {}).get("logical_type")
            if dataset.dataset_type == "settlement" and "settlement" not in layers:
                layers["settlement"] = str(path.resolve())
            elif dataset.dataset_type == "infrastructure" and logical_type in {"road", "bridge", "critical_infrastructure"} and logical_type not in layers:
                layers[logical_type] = str(path.resolve())
        return layers

    def _persist_native_analysis(self, db: Session, job: SimulationJob, native: dict, *, flood_threshold_m: float, source: str):
        output_dir = Path(native["water_depth_raster"]).resolve().parent
        result = process_result(
            water_depth_raster=native["water_depth_raster"],
            velocity_raster=native.get("velocity_raster"),
            arrival_time_raster=native.get("arrival_time_raster"),
            water_level_raster=native.get("water_level_raster"),
            dem_raster=str(self._native_dem_path(job)),
            discharge_csv=None,
            flood_threshold_m=flood_threshold_m,
            output_dir=output_dir,
            exposure_layers=self._native_exposure_layers(db, job.project_id),
        )
        result["exposure"] = complete_demo_exposure(result["exposure"], enabled=True)
        warnings = [*native.get("warnings", []), *result["warnings"]]
        metrics = {**native.get("summary", {}), **result["metrics"]}
        assumptions = {
            "analysis_version": f"phase8-native-{source}-v1",
            "source": f"native_{source}_result",
            "native_result_provenance": native.get("provenance", {}),
            "flood_threshold_m": flood_threshold_m,
            "source_inputs": {
                "working_directory": str(Path(job.working_directory or "").resolve()),
                "preprocessed_dem": str(self._native_dem_path(job)),
            },
        }
        existing_id = (job.result or {}).get("analysis_result_id")
        if existing_id:
            existing = self.results.get(db, existing_id)
            if existing is not None:
                return existing
        record = self.results.create(
            db,
            simulation_job_id=job.id,
            project_id=job.project_id,
            scenario_id=job.scenario_id,
            variant_id=job.variant_id,
            analysis_version=f"phase8-native-{source}-v1",
            flood_threshold_m=flood_threshold_m,
            metrics=metrics,
            exposure=result["exposure"],
            artifacts=result["artifacts"],
            warnings=warnings,
            assumptions=assumptions,
        )
        existing_job_result = dict(job.result or {})
        existing_job_result["analysis_result_id"] = record.id
        existing_job_result["postprocessing"] = {
            "status": "completed",
            "source": source,
            "analysis_version": record.analysis_version,
            "artifacts": result["artifacts"],
            "provenance": native.get("provenance", {}),
        }
        job.result = existing_job_result
        db.commit()
        db.refresh(job)
        return record

    def _native_dem_path(self, job: SimulationJob) -> Path:
        prepare = job.config or {}
        value = prepare.get("preprocessed_dem")
        if value:
            path = Path(value).resolve()
            if path.is_file():
                return path
        # Older releases persisted the modelling manifest even when the API job
        # config did not retain the DEM path. Recover the canonical preprocessing
        # artifact from that manifest so historical completed jobs remain processable.
        candidates: list[Path] = []
        if job.manifest_path:
            candidates.append(Path(job.manifest_path).resolve())
        if job.working_directory:
            candidates.append(Path(job.working_directory).resolve() / "hydroshield_model_manifest.json")
        for manifest_path in candidates:
            if not manifest_path.is_file():
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            manifest_dem = (payload.get("preprocessing_artifacts") or {}).get("dem")
            if manifest_dem:
                manifest_dem_path = Path(manifest_dem).resolve()
                if manifest_dem_path.is_file():
                    return manifest_dem_path
        if value:
            raise ConflictError(f"The persisted preprocessed DEM is not available: {Path(value).resolve()}")
        raise ConflictError(
            "The completed native job has no persisted preprocessed DEM path and its model manifest could not provide one."
        )

    def analyze_native_sph_job(self, db: Session, job_id: str, *, flood_threshold_m: float = 0.05, force: bool = False):
        job = db.get(SimulationJob, job_id)
        if job is None:
            raise NotFoundError("Simulation job not found.")
        postprocessing_failed = (job.result or {}).get("postprocessing", {}).get("status") == "failed"
        retryable_failure = (
            postprocessing_failed
            and not (job.result or {}).get("analysis_result_id")
            and job.status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value}
        )
        if job.status not in {JobStatus.COMPLETED.value, JobStatus.PROCESSING.value} and not retryable_failure:
            raise ConflictError(f"Simulation job must be completed, processing, or awaiting result-processing retry; current status is '{job.status}'.")
        if retryable_failure:
            job.status = JobStatus.PROCESSING.value
            job.current_step = "processing_native_results_retry"
            job.progress = 99.0
            job.error_message = None
            db.commit()
            db.refresh(job)
        if job.model != "sph":
            raise ConflictError("Automatic native-result processing for this endpoint requires an SPH job.")
        existing_id = (job.result or {}).get("analysis_result_id")
        if existing_id and not force:
            existing = self.results.get(db, existing_id)
            if existing is not None:
                return existing
        dem_path = self._native_dem_path(job)
        prepare = job.config or {}
        output_interval_s = float(prepare.get("sph_output_interval_s", 1.0))
        working_directory = Path(job.working_directory or "").resolve()
        if not working_directory.is_dir():
            raise ConflictError(f"Completed SPH working directory is not available: {working_directory}")
        native = build_sph_analysis_rasters(
            working_directory=working_directory,
            dem_path=dem_path,
            output_directory=working_directory / "analysis" / "native_sph",
            output_interval_s=output_interval_s,
            flood_threshold_m=flood_threshold_m,
        )
        return self._persist_native_analysis(db, job, native, flood_threshold_m=flood_threshold_m, source="sph")

    def analyze_native_delft3d_job(self, db: Session, job_id: str, *, flood_threshold_m: float = 0.05, force: bool = False):
        job = db.get(SimulationJob, job_id)
        if job is None:
            raise NotFoundError("Simulation job not found.")
        postprocessing_failed = (job.result or {}).get("postprocessing", {}).get("status") == "failed"
        retryable_failure = (
            postprocessing_failed
            and not (job.result or {}).get("analysis_result_id")
            and job.status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value}
        )
        if job.status not in {JobStatus.COMPLETED.value, JobStatus.PROCESSING.value} and not retryable_failure:
            raise ConflictError(f"Simulation job must be completed, processing, or awaiting result-processing retry; current status is '{job.status}'.")
        if retryable_failure:
            job.status = JobStatus.PROCESSING.value
            job.current_step = "processing_native_results_retry"
            job.progress = 99.0
            job.error_message = None
            db.commit()
            db.refresh(job)
        if job.model != "delft3d":
            raise ConflictError("Automatic native-result processing for this endpoint requires a Delft3D job.")
        existing_id = (job.result or {}).get("analysis_result_id")
        if existing_id and not force:
            existing = self.results.get(db, existing_id)
            if existing is not None:
                return existing
        dem_path = self._native_dem_path(job)
        working_directory = Path(job.working_directory or "").resolve()
        if not working_directory.is_dir():
            raise ConflictError(f"Completed Delft3D working directory is not available: {working_directory}")
        native = build_delft3d_analysis_rasters(
            working_directory=working_directory,
            dem_path=dem_path,
            output_directory=working_directory / "analysis" / "native_delft3d",
            flood_threshold_m=flood_threshold_m,
        )
        return self._persist_native_analysis(db, job, native, flood_threshold_m=flood_threshold_m, source="delft3d")

    def analyze_native_job(self, db: Session, job_id: str, *, flood_threshold_m: float = 0.05, force: bool = False):
        job = db.get(SimulationJob, job_id)
        if job is None:
            raise NotFoundError("Simulation job not found.")
        if job.model not in {"sph", "delft3d"}:
            raise ConflictError(f"Automatic native-result processing is not supported for model '{job.model}'.")
        try:
            if job.model == "sph":
                result = self.analyze_native_sph_job(db, job_id, flood_threshold_m=flood_threshold_m, force=force)
            else:
                result = self.analyze_native_delft3d_job(db, job_id, flood_threshold_m=flood_threshold_m, force=force)
            refreshed = db.get(SimulationJob, job_id)
            if refreshed is not None:
                payload = dict(refreshed.result or {})
                payload["analysis_result_id"] = result.id
                payload["postprocessing"] = {
                    **dict(payload.get("postprocessing") or {}),
                    "status": "completed",
                    "analysis_result_id": result.id,
                    "analysis_version": result.analysis_version,
                    "artifacts": result.artifacts,
                }
                payload["native_analysis"] = dict(payload["postprocessing"])
                refreshed.result = payload
                refreshed.status = JobStatus.COMPLETED.value
                refreshed.current_step = "complete"
                refreshed.progress = 100.0
                refreshed.error_message = None
                db.commit()
                db.refresh(refreshed)
            return result
        except Exception as exc:
            refreshed = db.get(SimulationJob, job_id)
            if refreshed is not None and refreshed.current_step in {"processing_native_results_retry", "processing_native_results", "result_processing_failed"}:
                payload = dict(refreshed.result or {})
                payload["postprocessing"] = {"status": "failed", "error": str(exc)}
                payload["native_analysis"] = dict(payload["postprocessing"])
                refreshed.result = payload
                refreshed.status = JobStatus.FAILED.value
                refreshed.current_step = "result_processing_failed"
                refreshed.progress = 99.0
                refreshed.error_message = f"{refreshed.model.upper()} solver completed, but HydroShield result processing failed: {exc}"
                db.commit()
            raise

    def analyze_job(self, db: Session, job_id: str, payload: ResultAnalysisRequest):
        job = self._job(db, job_id)
        output_dir = Path(payload.output_directory) if payload.output_directory else Path(job.working_directory or "data/analysis") / "analysis"
        result = process_result(
            water_depth_raster=payload.water_depth_raster,
            velocity_raster=payload.velocity_raster,
            arrival_time_raster=payload.arrival_time_raster,
            water_level_raster=payload.water_level_raster,
            dem_raster=payload.dem_raster,
            discharge_csv=payload.discharge_csv,
            flood_threshold_m=payload.flood_threshold_m,
            output_dir=output_dir,
            exposure_layers=payload.exposure_layers,
        )
        result["exposure"] = complete_demo_exposure(result["exposure"], enabled=True)
        assumptions = {
            "analysis_version": ANALYSIS_VERSION,
            "source_inputs": {
                "water_depth_raster": str(Path(payload.water_depth_raster).resolve()),
                "velocity_raster": str(Path(payload.velocity_raster).resolve()) if payload.velocity_raster else None,
                "arrival_time_raster": str(Path(payload.arrival_time_raster).resolve()) if payload.arrival_time_raster else None,
                "water_level_raster": str(Path(payload.water_level_raster).resolve()) if payload.water_level_raster else None,
                "dem_raster": str(Path(payload.dem_raster).resolve()) if payload.dem_raster else None,
                "discharge_csv": str(Path(payload.discharge_csv).resolve()) if payload.discharge_csv else None,
                "exposure_layers": {k: str(Path(v).resolve()) for k, v in payload.exposure_layers.items()},
            },
            "flood_threshold_m": payload.flood_threshold_m,
            "inundated_area_method": "flooded_pixel_count_times_projected_pixel_area",
            "flood_extent_method": "polygonize_water_depth_threshold_mask",
            "max_water_level_method": "provided_water_level_raster_or_dem_plus_depth",
            "comparison_method": "common_reference_grid_with_bilinear_continuous_resampling",
            "prototype_exposure_fallback": bool(get_settings().demo_mode and any((layer or {}).get("fallback") for layer in result["exposure"].get("layers", {}).values())),
        }
        record = self.results.create(
            db,
            simulation_job_id=job.id,
            project_id=job.project_id,
            scenario_id=job.scenario_id,
            variant_id=job.variant_id,
            analysis_version=ANALYSIS_VERSION,
            flood_threshold_m=payload.flood_threshold_m,
            metrics=result["metrics"],
            exposure=result["exposure"],
            artifacts=result["artifacts"],
            warnings=result["warnings"],
            assumptions=assumptions,
        )
        existing_job_result = dict(job.result or {})
        existing_job_result["analysis_result_id"] = record.id
        job.result = existing_job_result
        db.commit()
        db.refresh(job)
        return record

    def get_result(self, db: Session, result_id: str):
        record = self.results.get(db, result_id)
        if record is None:
            raise NotFoundError("Analysis result not found.")
        return record

    def list_for_job(self, db: Session, job_id: str):
        self._job(db, job_id)
        return self.results.list_for_job(db, job_id)

    def compare(self, db: Session, payload: ResultComparisonRequest):
        left = self.results.get(db, payload.left_analysis_id)
        right = self.results.get(db, payload.right_analysis_id)
        if left is None or right is None:
            raise NotFoundError("One or both analysis results were not found.")
        if left.project_id != right.project_id:
            raise ConflictError("Compared analysis results must belong to the same project.")
        if left.id == right.id:
            raise ConflictError("An analysis result cannot be compared with itself.")
        if abs(left.flood_threshold_m - right.flood_threshold_m) > 1e-9:
            raise ConflictError("Compared analysis results must use the same flood-depth threshold.")
        if payload.comparison_type == ComparisonType.MODEL:
            if left.variant_id != right.variant_id:
                raise ConflictError("Model comparison requires the same scenario variant and different model runs.")
            if left.simulation_job.model == right.simulation_job.model:
                raise ConflictError("Model comparison requires different model runs, such as SPH versus Delft3D.")
        if payload.comparison_type == ComparisonType.SCENARIO:
            if left.simulation_job.model != right.simulation_job.model:
                raise ConflictError("Scenario comparison requires the same hydrodynamic model so scenario differences are isolated.")
            if left.variant_id == right.variant_id:
                raise ConflictError("Scenario comparison requires two different scenario variants.")
            if left.scenario_id == right.scenario_id and left.variant_id == right.variant_id:
                raise ConflictError("Scenario comparison requires distinct scenario variants.")
        output_dir = Path(payload.output_directory) if payload.output_directory else Path("data/analysis/comparisons") / f"{left.id}_vs_{right.id}"
        metrics = compare_analysis_artifacts(
            left_depth_path=left.artifacts["water_depth_raster"],
            right_depth_path=right.artifacts["water_depth_raster"],
            left_velocity_path=left.artifacts.get("velocity_raster"),
            right_velocity_path=right.artifacts.get("velocity_raster"),
            left_arrival_path=left.artifacts.get("arrival_time_raster"),
            right_arrival_path=right.artifacts.get("arrival_time_raster"),
            flood_threshold_m=left.flood_threshold_m,
            output_dir=output_dir,
        )
        assumptions = {
            "comparison_type": payload.comparison_type.value,
            "reference_analysis": left.id,
            "continuous_alignment": "right_resampled_to_left_depth_grid",
            "difference_definition": "right_minus_left",
        }
        return self.comparisons.create(
            db,
            project_id=left.project_id,
            left_analysis_id=left.id,
            right_analysis_id=right.id,
            comparison_type=payload.comparison_type.value,
            metrics=metrics["metrics"],
            artifacts=metrics["artifacts"],
            warnings=metrics["warnings"],
            assumptions=assumptions,
        )

    def get_comparison(self, db: Session, comparison_id: str):
        record = self.comparisons.get(db, comparison_id)
        if record is None:
            raise NotFoundError("Result comparison not found.")
        return record
