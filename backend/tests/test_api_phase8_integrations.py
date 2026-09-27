from __future__ import annotations

import io
from types import SimpleNamespace

import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database.base import Base
from app.database.models import Project, Scenario, ScenarioVariant, SimulationJob
from app.database.session import get_db
from app.main import create_app


class DummyJobManager:
    def recover_pending(self):
        return 0

    def shutdown(self, wait=False):
        return None


def depth_file(path, value):
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32",
                       crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=-9999) as dst:
        dst.write(np.full((2, 2), value, dtype="float32"), 1)


def make_db(tmp_path, model="sph"):
    engine = create_engine(f"sqlite:///{tmp_path / 'api8.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name=f"API8 {model}"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="Scenario", model=model, config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model=model, parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model=model, status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    return engine, SessionLocal, project, scenario, variant, job


def test_upload_and_compare_routes(tmp_path, monkeypatch):
    engine, SessionLocal, project, scenario, variant, job = make_db(tmp_path)
    depth = tmp_path / "depth.tif"; depth_file(depth, 0.5)
    app = create_app()
    app.state.job_manager = DummyJobManager()
    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.api.routes.dataset_uploads.get_settings", lambda: SimpleNamespace(storage_root=tmp_path / "uploads"))

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{project.id}/datasets/upload",
            data={"dataset_type": "dem"},
            files={"file": ("dem.tif", io.BytesIO(depth.read_bytes()), "image/tiff")},
        )
        assert response.status_code == 201
        stored = response.json()["storage_uri"]
        assert stored.startswith(str((tmp_path / "uploads").resolve()))
        assert __import__('pathlib').Path(stored).exists()

        analysis = client.post(
            f"/api/v1/results/simulations/{job.id}/analyze",
            json={"water_depth_raster": str(depth), "flood_threshold_m": 0.05},
        )
        assert analysis.status_code == 201
        result_id = analysis.json()["id"]
        fetched = client.get(f"/api/v1/results/{result_id}")
        assert fetched.status_code == 200
        listed = client.get(f"/api/v1/results/simulations/{job.id}")
        assert listed.status_code == 200 and len(listed.json()) == 1

    engine.dispose()
