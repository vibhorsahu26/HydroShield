
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant, SimulationJob
from app.schemas.satellite import ObservationPhase, SatelliteSensor, SatelliteValidationRequest
from app.services.satellite_service import SatelliteValidationService
from app.satellite.gee import EarthEngineUnavailable


@dataclass
class UnavailableProvider:
    def observe(self, **kwargs):
        raise EarthEngineUnavailable("Earth Engine could not be initialized.")


def _raster(path: Path, data: np.ndarray):
    with rasterio.open(
        path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
        dtype="uint8", crs="EPSG:32643", transform=from_origin(0, 40, 10, 10), nodata=255
    ) as dst:
        dst.write(data.astype("uint8"), 1)


def test_satellite_falls_back_when_external_provider_is_unavailable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fallback.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()

    project = Project(name="Fallback")
    db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="Scenario", model="sph", config={})
    db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(
        base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach",
        model="sph", parameters={}, assumptions={}
    )
    db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(
        project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph",
        status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1,
        timeout_s=60, config={}, cancel_requested=False, result={}
    )
    db.add(job); db.commit(); db.refresh(job)

    model_mask = tmp_path / "model_mask.tif"
    _raster(model_mask, np.array([[1,1,0,0],[1,1,0,0],[0,0,0,0],[0,0,0,0]], dtype=np.uint8))
    extent = tmp_path / "extent.geojson"
    gpd.GeoDataFrame(
        {"flooded":[1]}, geometry=[gpd.GeoSeries.from_wkt(["POLYGON ((0 0, 20 0, 20 20, 0 20, 0 0))"])[0]],
        crs="EPSG:32643"
    ).to_file(extent, driver="GeoJSON")
    analysis = AnalysisResult(
        simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id,
        analysis_version="phase8", flood_threshold_m=0.05, metrics={}, exposure={},
        artifacts={"flood_mask_raster": str(model_mask), "flood_extent_geojson": str(extent)},
        warnings=[], assumptions={}
    )
    db.add(analysis); db.commit(); db.refresh(analysis)

    payload = SatelliteValidationRequest(
        analysis_result_id=analysis.id, sensor=SatelliteSensor.SENTINEL1,
        phase=ObservationPhase.DURING, start_date=date(2026,1,1), end_date=date(2026,1,2)
    )
    record = SatelliteValidationService(provider=UnavailableProvider()).validate(db, payload)
    assert record.image_count == 3
    assert record.source_metadata["provider"] == "DemoSatelliteProvider"
    assert record.source_metadata["external_provider_failed"] is True
    assert record.observed_extent_path
    assert Path(record.observed_extent_path).is_file()
    db.close(); engine.dispose()
