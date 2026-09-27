from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.session import get_db
from app.api.routes import modelling
from app.main import create_app


def test_prepare_sph_variant_from_persisted_phase5_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase6.db'}", connect_args={"check_same_thread": False})
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
    client = TestClient(app)
    try:
        project = client.post("/api/v1/projects", json={"name": "Phase6 API"})
        pid = project.json()["id"]
        scenario = client.post(
            f"/api/v1/projects/{pid}/scenarios",
            json={
                "name": "Base",
                "initial_reservoir_water_level_m": 120,
                "reservoir_volume_m3": 5000000,
                "breach_width_m": 40,
                "breach_depth_m": 20,
                "breach_formation_time_s": 300,
                "initial_discharge_m3s": 200,
                "simulation_duration_s": 3600,
                "model": "both",
            },
        )
        sid = scenario.json()["id"]
        generated = client.post(
            f"/api/v1/projects/{pid}/scenarios/{sid}/variants/generate",
            json={"presets": ["major_breach"]},
        )
        vid = generated.json()["variants"][0]["code"]

        # Resolve actual persisted variant id through listing endpoint.
        listed = client.get(f"/api/v1/projects/{pid}/scenarios/{sid}/variants").json()
        variant_id = next(item["id"] for item in listed if item["code"] == vid)
        native = tmp_path / "sph_native"
        native.mkdir()
        (native / "Case_Def.xml").write_text("<case><metadata><duration>{HYDROSHIELD_TIME_MAX_S}</duration></metadata></case>", encoding="utf-8")
        dem = tmp_path / "processed_dem.tif"; river = tmp_path / "prepared_river.gpkg"; domain = tmp_path / "computational_domain.gpkg"; mask = tmp_path / "domain_mask.tif"
        for artifact in (dem, river, domain, mask): artifact.write_bytes(b"artifact")
        modelling.service.dual_sph_gencase = ["python", "-c", "pass"]
        modelling.service.dual_sph_solver_gpu = ["python", "-c", "pass"]
        modelling.service.dual_sph_partvtk = ["python", "-c", "pass"]

        response = client.post(
            f"/api/v1/modelling/projects/{pid}/scenarios/{sid}/variants/{variant_id}/prepare/sph",
            json={"native_input_directory": str(native), "working_directory": str(tmp_path / "model_run"), "preprocessed_dem": str(dem), "prepared_river": str(river), "computational_domain": str(domain), "domain_mask": str(mask)},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["model"] == "sph"
        manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
        assert manifest["variant_parameters"]["breach_width_m"] == 20
        assert manifest["preprocessing_artifacts"]["dem"] == str(dem)
        assert payload["command"][0] == "python"
        assert len(payload["execution_steps"]) == 3
    finally:
        client.close()
        engine.dispose()
        modelling.service.dual_sph_gencase = None
        modelling.service.dual_sph_solver_gpu = None
        modelling.service.dual_sph_partvtk = None


def test_prepare_rejects_missing_upstream_artifact(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase6-missing.db'}", connect_args={"check_same_thread": False})
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
    client = TestClient(app)
    try:
        pid = client.post("/api/v1/projects", json={"name": "Missing Artifact"}).json()["id"]
        sid = client.post(f"/api/v1/projects/{pid}/scenarios", json={
            "name": "Base", "initial_reservoir_water_level_m": 120, "reservoir_volume_m3": 100000,
            "breach_width_m": 20, "breach_depth_m": 10, "breach_formation_time_s": 100,
            "initial_discharge_m3s": 50, "simulation_duration_s": 1000, "model": "sph"
        }).json()["id"]
        body = client.post(f"/api/v1/projects/{pid}/scenarios/{sid}/variants/generate", json={"presets": ["major_breach"]}).json()
        variant_id = client.get(f"/api/v1/projects/{pid}/scenarios/{sid}/variants").json()[0]["id"]
        response = client.post(f"/api/v1/modelling/projects/{pid}/scenarios/{sid}/variants/{variant_id}/prepare/sph", json={
            "native_input_directory": str(tmp_path / "native"), "preprocessed_dem": str(tmp_path / "missing.tif")
        })
        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]
    finally:
        client.close(); engine.dispose()
