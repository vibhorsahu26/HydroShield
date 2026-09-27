from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import modelling
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app


def _write_dem(path: Path) -> None:
    with rasterio.open(path, "w", driver="GTiff", height=3, width=3, count=1, dtype="float32", crs="EPSG:32643", transform=from_origin(500_000, 3_000_000, 20, 20)) as dst:
        dst.write(np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5]], dtype=np.float32), 1)


def _build_client(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auto-model.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return engine, TestClient(app)


def test_prepare_sph_can_generate_case_without_native_case_upload(tmp_path):
    engine, client = _build_client(tmp_path)
    try:
        project_id = client.post("/api/v1/projects", json={"name": "Auto model"}).json()["id"]
        scenario_id = client.post(f"/api/v1/projects/{project_id}/scenarios", json={
            "name": "Base", "initial_reservoir_water_level_m": 120, "reservoir_volume_m3": 100000,
            "breach_width_m": 20, "breach_depth_m": 10, "breach_formation_time_s": 100,
            "initial_discharge_m3s": 10, "simulation_duration_s": 1000, "model": "sph"
        }).json()["id"]
        client.post(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants/generate", json={"presets": ["major_breach"]})
        variant_id = client.get(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants").json()[0]["id"]
        dem = tmp_path / "processed_dem.tif"
        _write_dem(dem)
        response = client.post(f"/api/v1/modelling/projects/{project_id}/scenarios/{scenario_id}/variants/{variant_id}/prepare/sph", json={
            "auto_generate": True,
            "working_directory": str(tmp_path / "run"),
            "preprocessed_dem": str(dem),
            "sph_device": "cpu",
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["native_input_directory"]
        assert Path(payload["native_input_directory"], "Case_Def.xml").exists()
        assert payload["warnings"]
    finally:
        client.close(); engine.dispose()


def test_prepare_requires_native_input_when_automatic_generation_disabled(tmp_path):
    engine, client = _build_client(tmp_path)
    try:
        project_id = client.post("/api/v1/projects", json={"name": "Manual contract"}).json()["id"]
        scenario_id = client.post(f"/api/v1/projects/{project_id}/scenarios", json={
            "name": "Base", "initial_reservoir_water_level_m": 120, "reservoir_volume_m3": 100000,
            "breach_width_m": 20, "breach_depth_m": 10, "breach_formation_time_s": 100,
            "initial_discharge_m3s": 10, "simulation_duration_s": 1000, "model": "sph"
        }).json()["id"]
        client.post(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants/generate", json={"presets": ["major_breach"]})
        variant_id = client.get(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants").json()[0]["id"]
        response = client.post(f"/api/v1/modelling/projects/{project_id}/scenarios/{scenario_id}/variants/{variant_id}/prepare/sph", json={"auto_generate": False})
        assert response.status_code == 400
        assert "native_input_directory" in response.json()["detail"]
    finally:
        client.close(); engine.dispose()


def test_prepare_delft3d_can_generate_case_without_native_case_upload(tmp_path):
    engine, client = _build_client(tmp_path)
    try:
        project_id = client.post("/api/v1/projects", json={"name": "Auto Delft3D"}).json()["id"]
        scenario_id = client.post(f"/api/v1/projects/{project_id}/scenarios", json={
            "name": "Base", "initial_reservoir_water_level_m": 120, "reservoir_volume_m3": 100000,
            "breach_width_m": 20, "breach_depth_m": 10, "breach_formation_time_s": 100,
            "initial_discharge_m3s": 10, "simulation_duration_s": 1000, "model": "delft3d"
        }).json()["id"]
        client.post(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants/generate", json={"presets": ["major_breach"]})
        variant_id = client.get(f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants").json()[0]["id"]
        dem = tmp_path / "processed_dem.tif"
        _write_dem(dem)
        response = client.post(f"/api/v1/modelling/projects/{project_id}/scenarios/{scenario_id}/variants/{variant_id}/prepare/delft3d", json={
            "auto_generate": True,
            "working_directory": str(tmp_path / "run"),
            "preprocessed_dem": str(dem),
            "delft3d_runner_mode": "dimr",
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        native = Path(payload["native_input_directory"])
        assert (native / "dimr_config.xml").exists()
        assert (native / "hydroshield.mdu").exists()
        assert (native / "hydroshield_net.nc").exists()
        assert payload["execution_steps"] == []
    finally:
        client.close(); engine.dispose()
