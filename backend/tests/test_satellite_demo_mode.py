from __future__ import annotations

from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant, SimulationJob
from app.schemas.satellite import ObservationPhase, SatelliteSensor, SatelliteValidationRequest
from app.services.satellite_service import SatelliteValidationService


def write_model_mask(path: Path) -> None:
    with rasterio.open(
        path, "w", driver="GTiff", width=20, height=20, count=1, dtype="uint8",
        crs="EPSG:32643", transform=rasterio.transform.from_origin(500000, 3000000, 100, 100), nodata=255,
    ) as dst:
        data = np.zeros((20, 20), dtype="uint8")
        data[6:14, 5:15] = 1
        dst.write(data, 1)


def test_demo_satellite_provider_generates_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        mask = tmp_path / "model.tif"
        extent = tmp_path / "extent.geojson"
        observed = tmp_path / "observed.tif"
        write_model_mask(mask)
        gpd.GeoDataFrame({"water": [1]}, geometry=[box(500500, 2998600, 501500, 2999400)], crs="EPSG:32643").to_file(extent, driver="GeoJSON")

        service = SatelliteValidationService()
        observation = service.provider.observe(
            roi_geojson=str(extent),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            sensor="sentinel1",
            output_path=observed,
            scale_m=30,
            temporal_reducer="max",
            s2_cloud_pct=60,
            s2_threshold=0.2,
            target_crs="EPSG:32643",
        )
        assert observation.collection_id == "HYDROSHIELD/SATELLITE/OBSERVED"
        assert observation.image_count == 3
        assert observed.exists()
        with rasterio.open(observed) as src:
            assert src.crs.to_string() == "EPSG:32643"
            assert src.read(1).sum() > 0
    finally:
        get_settings.cache_clear()


def test_demo_satellite_validation_service_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        engine = create_engine(f"sqlite:///{tmp_path / 'demo-sat.db'}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()

        project = Project(name="Demo Satellite Project"); db.add(project); db.commit(); db.refresh(project)
        scenario = Scenario(project_id=project.id, name="Demo flood", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
        variant = ScenarioVariant(base_scenario_id=scenario.id, code="major", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
        job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=60, config={}, cancel_requested=False, result={}); db.add(job); db.commit(); db.refresh(job)

        model = tmp_path / "model-mask.tif"; extent = tmp_path / "extent.geojson"; write_model_mask(model)
        gpd.GeoDataFrame({"water": [1]}, geometry=[box(500500, 2998600, 501500, 2999400)], crs="EPSG:32643").to_file(extent, driver="GeoJSON")
        analysis = AnalysisResult(
            simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id,
            analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={},
            artifacts={"flood_mask_raster": str(model), "flood_extent_geojson": str(extent)}, warnings=[], assumptions={}
        )
        db.add(analysis); db.commit(); db.refresh(analysis)

        record = SatelliteValidationService().validate(db, SatelliteValidationRequest(
            analysis_result_id=analysis.id, sensor=SatelliteSensor.SENTINEL1,
            phase=ObservationPhase.DURING, start_date=date(2026, 1, 1), end_date=date(2026, 1, 2),
        ))
        assert record.collection_id == "HYDROSHIELD/SATELLITE/OBSERVED"
        assert record.image_count == 3
        assert 0 < record.metrics["iou"] < 0.99
        assert 0 < record.metrics["precision"] < 1
        assert 0 < record.metrics["recall"] < 1
        assert Path(record.observed_extent_path).exists()
        assert Path(record.difference_map_path).exists()
        assert record.assumptions["sensor"] == "sentinel1"
        db.close(); engine.dispose()
    finally:
        get_settings.cache_clear()
