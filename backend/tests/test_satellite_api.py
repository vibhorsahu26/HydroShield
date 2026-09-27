from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant, SimulationJob
from app.database.session import get_db
from app.main import create_app
from app.schemas.satellite import SatelliteSensor


@dataclass
class FakeObservation:
    collection_id: str = "OPERA/DSWX/L3_V1/S1"
    image_count: int = 1
    selected_image_ids: list[str] | None = None
    processing_method: str = "fake"
    warnings: list[str] | None = None
    downloaded_path: Path | None = None

    def __post_init__(self):
        self.selected_image_ids = self.selected_image_ids or ["fake-1"]
        self.warnings = self.warnings or []


class FakeProvider:
    def __init__(self, path: Path):
        self.path = path

    def observe(self, **kwargs):
        return FakeObservation(downloaded_path=self.path)


class DummyJobManager:
    def recover_pending(self):
        return 0

    def shutdown(self, wait=False):
        return None


def raster(path, data):
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="uint8",
                       crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=255) as dst:
        dst.write(np.array(data, dtype="uint8"), 1)


def test_satellite_validation_api_with_injected_provider(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Satellite API Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="Scenario", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=60, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    model = tmp_path / "model.tif"; observed = tmp_path / "observed.tif"; extent = tmp_path / "extent.geojson"
    raster(model, [[1, 1], [0, 0]])
    raster(observed, [[1, 0], [0, 1]])
    extent.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    analysis = AnalysisResult(simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id,
                              analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={},
                              artifacts={"flood_mask_raster": str(model), "flood_extent_geojson": str(extent)}, warnings=[], assumptions={})
    db.add(analysis); db.commit(); db.refresh(analysis)
    db.close()

    app = create_app()
    app.state.job_manager = DummyJobManager()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    from app.api.routes.satellite import get_service
    app.dependency_overrides[get_service] = lambda: __import__('app.services.satellite_service', fromlist=['SatelliteValidationService']).SatelliteValidationService(provider=FakeProvider(observed))
    with TestClient(app) as client:
        response = client.post('/api/v1/satellite/validate', json={
            'analysis_result_id': analysis.id,
            'sensor': SatelliteSensor.SENTINEL1.value,
            'phase': 'during',
            'start_date': '2026-01-01',
            'end_date': '2026-01-02',
        })
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload['metrics']['iou'] == 1 / 3
        assert payload['collection_id'] == 'OPERA/DSWX/L3_V1/S1'

    engine.dispose()


def test_satellite_observed_extent_preview(tmp_path):
    import json
    import geopandas as gpd
    from shapely.geometry import box
    from app.database.repositories.satellite import SatelliteValidationRepository

    engine = create_engine(f"sqlite:///{tmp_path / 'satellite-preview.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Satellite Preview Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = __import__('app.database.models', fromlist=['Scenario']).Scenario(project_id=project.id, name="Scenario", model="sph", config={})
    db.add(scenario); db.commit(); db.refresh(scenario)
    variant = __import__('app.database.models', fromlist=['ScenarioVariant']).ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={})
    db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=60, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    analysis = AnalysisResult(simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, analysis_version="phase8-v1", flood_threshold_m=.05, metrics={}, exposure={}, artifacts={"flood_mask_raster":"/tmp/flood.tif","flood_extent_geojson":"/tmp/ext.geojson"}, warnings=[], assumptions={})
    db.add(analysis); db.commit(); db.refresh(analysis)
    extent = tmp_path / "observed.geojson"
    gpd.GeoDataFrame({"water":[1]}, geometry=[box(10,10,20,20)], crs="EPSG:4326").to_file(extent, driver="GeoJSON")
    difference = tmp_path / "difference.tif"
    with rasterio.open(difference, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32", crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=-9999) as dst:
        dst.write(np.array([[1, 0], [0, -1]], dtype="float32"), 1)
    record = SatelliteValidationRepository().create(db, simulation_job_id=job.id, analysis_result_id=analysis.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, sensor="sentinel1", phase="during", collection_id="fake", start_date=__import__('datetime').datetime(2026,1,1), end_date=__import__('datetime').datetime(2026,1,2), image_count=1, selected_image_ids=["x"], metrics={"iou":.5}, observed_extent_path=str(extent), difference_map_path=str(difference), source_metadata={}, warnings=[], assumptions={})
    db.commit(); db.refresh(record); db.close()
    from app.main import create_app
    from app.database.session import get_db
    app = create_app()
    def override_db():
        session = SessionLocal()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.get(f"/api/v1/satellite/validations/{record.id}/observed-extent")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) == 1
        difference_preview = client.get(f"/api/v1/satellite/validations/{record.id}/difference-preview")
        assert difference_preview.status_code == 200, difference_preview.text
        assert "bounds" in difference_preview.json()
    engine.dispose()
