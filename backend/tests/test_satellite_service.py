from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant, SimulationJob
from app.schemas.satellite import ObservationPhase, SatelliteSensor, SatelliteValidationRequest
from app.services.satellite_service import SatelliteValidationService


@dataclass
class FakeObservation:
    collection_id: str
    image_count: int
    selected_image_ids: list[str]
    processing_method: str
    warnings: list[str]
    downloaded_path: Path


class FakeProvider:
    def __init__(self, observed_path: Path):
        self.observed_path = observed_path

    def observe(self, **kwargs):
        return FakeObservation("FAKE/S1", 2, ["a", "b"], "fake-provider", [], self.observed_path)


def raster(path, data):
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="uint8", crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=255) as dst:
        dst.write(np.array(data, dtype="uint8"), 1)


def test_phase8_to_phase9_service_integration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sat.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    project = Project(name="Satellite Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="During flood", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="major", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=60, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)

    model = tmp_path / "model_mask.tif"; observed = tmp_path / "observed.tif"; extent = tmp_path / "extent.geojson"
    raster(model, [[1, 1], [0, 0]])
    raster(observed, [[1, 0], [0, 1]])
    extent.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    analysis = AnalysisResult(simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id,
                              analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={},
                              artifacts={"flood_mask_raster": str(model), "flood_extent_geojson": str(extent)}, warnings=[], assumptions={})
    db.add(analysis); db.commit(); db.refresh(analysis)

    service = SatelliteValidationService(provider=FakeProvider(observed))
    payload = SatelliteValidationRequest(analysis_result_id=analysis.id, sensor=SatelliteSensor.SENTINEL1,
                                         phase=ObservationPhase.DURING, start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    record = service.validate(db, payload)
    assert record.collection_id == "FAKE/S1"
    assert record.metrics["iou"] == 1 / 3
    assert record.analysis_result_id == analysis.id
    db.close(); engine.dispose()
