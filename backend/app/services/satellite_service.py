from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.database.models import AnalysisResult, SimulationJob
from app.database.repositories.satellite import SatelliteValidationRepository
from app.satellite.comparison import compare_predicted_observed
from app.satellite.gee import EarthEngineSatelliteProvider, EarthEngineUnavailable
from app.satellite.demo import DemoSatelliteProvider
from app.core.config import get_settings
from app.schemas.satellite import SatelliteValidationRequest


class SatelliteValidationService:
    VERSION = "phase9-v1"

    def __init__(self, provider: EarthEngineSatelliteProvider | None = None):
        settings = get_settings()
        self.provider = provider or (DemoSatelliteProvider() if settings.demo_mode else EarthEngineSatelliteProvider(ee_project=settings.earth_engine_project))
        self.repository = SatelliteValidationRepository()

    def validate(self, db: Session, payload: SatelliteValidationRequest):
        analysis = db.get(AnalysisResult, payload.analysis_result_id)
        if analysis is None:
            raise NotFoundError("Analysis result not found.")
        job = db.get(SimulationJob, analysis.simulation_job_id)
        if job is None:
            raise NotFoundError("Simulation job not found for analysis result.")
        model_mask = analysis.artifacts.get("flood_mask_raster")
        model_extent = analysis.artifacts.get("flood_extent_geojson")
        if not model_mask or not model_extent:
            raise ConflictError("Analysis result does not contain the flood mask and extent required for satellite validation.")

        output_dir = Path(payload.output_directory) if payload.output_directory else Path("data/satellite") / analysis.id / payload.phase.value
        observed_path = output_dir / "observed_water.tif"
        observation_provider = self.provider
        fallback_used = False
        fallback_reason = None
        try:
            observation = observation_provider.observe(
                roi_geojson=model_extent,
                start_date=payload.start_date,
                end_date=payload.end_date,
                sensor=payload.sensor.value,
                output_path=observed_path,
                scale_m=payload.scale_m,
                temporal_reducer=payload.temporal_reducer,
                s2_cloud_pct=payload.sentinel2_cloud_pct,
                s2_threshold=payload.sentinel2_mndwi_threshold,
                target_crs=str(analysis_crs(model_mask)),
            )
        except ValueError as exc:
            if not isinstance(observation_provider, EarthEngineSatelliteProvider) or "imagery found" not in str(exc).lower():
                raise
            fallback_used = True
            fallback_reason = str(exc)
            observation_provider = DemoSatelliteProvider()
            observation = observation_provider.observe(
                roi_geojson=model_extent,
                start_date=payload.start_date,
                end_date=payload.end_date,
                sensor=payload.sensor.value,
                output_path=observed_path,
                scale_m=payload.scale_m,
                temporal_reducer=payload.temporal_reducer,
                s2_cloud_pct=payload.sentinel2_cloud_pct,
                s2_threshold=payload.sentinel2_mndwi_threshold,
                target_crs=str(analysis_crs(model_mask)),
            )
        except EarthEngineUnavailable as exc:
            # Keep validation usable when Earth Engine credentials/project are
            # not configured. The generated observation still follows the same
            # comparison/export contract as a real satellite result.
            fallback_used = True
            fallback_reason = str(exc)
            observation_provider = DemoSatelliteProvider()
            observation = observation_provider.observe(
                roi_geojson=model_extent,
                start_date=payload.start_date,
                end_date=payload.end_date,
                sensor=payload.sensor.value,
                output_path=observed_path,
                scale_m=payload.scale_m,
                temporal_reducer=payload.temporal_reducer,
                s2_cloud_pct=payload.sentinel2_cloud_pct,
                s2_threshold=payload.sentinel2_mndwi_threshold,
                target_crs=str(analysis_crs(model_mask)),
            )
        comparison = compare_predicted_observed(
            model_mask_path=model_mask,
            observed_mask_path=str(observation.downloaded_path),
            output_dir=output_dir,
        )
        assumptions = {
            "version": self.VERSION,
            "phase": payload.phase.value,
            "sensor": payload.sensor.value,
            "collection_id": observation.collection_id,
            "temporal_reducer": payload.temporal_reducer,
            "satellite_to_model_alignment": "nearest-neighbor to model flood-mask grid",
            "difference_definition": "observed minus model; -1=model-only, 0=overlap, +1=observed-only",
            "model_extent_roi": str(Path(model_extent).resolve()),
            "model_flood_mask": str(Path(model_mask).resolve()),
            "sentinel2_mndwi_threshold": payload.sentinel2_mndwi_threshold,
        }
        record = self.repository.create(
            db,
            simulation_job_id=job.id,
            analysis_result_id=analysis.id,
            project_id=analysis.project_id,
            scenario_id=analysis.scenario_id,
            variant_id=analysis.variant_id,
            sensor=payload.sensor.value,
            phase=payload.phase.value,
            collection_id=observation.collection_id,
            start_date=datetime.combine(payload.start_date, datetime.min.time(), tzinfo=timezone.utc),
            end_date=datetime.combine(payload.end_date, datetime.min.time(), tzinfo=timezone.utc),
            image_count=observation.image_count,
            selected_image_ids=observation.selected_image_ids,
            metrics=comparison["metrics"],
            observed_extent_path=comparison["observed_extent_path"],
            difference_map_path=comparison["difference_map_path"],
            source_metadata={"processing_method": observation.processing_method, "provider": observation_provider.__class__.__name__, "external_provider_failed": fallback_used, "fallback_reason": fallback_reason},
            warnings=[*observation.warnings, *([f'External satellite provider unavailable: {fallback_reason}.'] if fallback_used and fallback_reason else [])],
            assumptions=assumptions,
        )
        return record


def analysis_crs(model_mask_path: str) -> str:
    import rasterio
    with rasterio.open(model_mask_path) as src:
        if src.crs is None:
            raise ConflictError("Model flood mask has no CRS.")
        return src.crs.to_string()
