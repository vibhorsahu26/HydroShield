from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.session import get_db
from app.main import create_app


def make_client(tmp_path):
    db_path = tmp_path / "phase5.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
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
    return TestClient(app), engine


def valid_base_scenario():
    return {
        "name": "Base Scenario",
        "initial_reservoir_water_level_m": 120,
        "reservoir_volume_m3": 5_000_000,
        "breach_width_m": 40,
        "breach_depth_m": 20,
        "breach_formation_time_s": 300,
        "initial_discharge_m3s": 200,
        "simulation_duration_s": 3600,
        "model": "both",
    }


def test_generate_and_list_variants_integrates_phase3_persistence_and_phase1_validation(tmp_path):
    client, engine = make_client(tmp_path)
    try:
        project = client.post("/api/v1/projects", json={"name": "Phase 5 Basin"})
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        base = client.post(
            f"/api/v1/projects/{project_id}/scenarios",
            json=valid_base_scenario(),
        )
        assert base.status_code == 201, base.text
        scenario_id = base.json()["id"]

        generated = client.post(
            f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants/generate",
            json={
                "presets": ["partial_breach", "major_breach", "extreme_breach", "controlled_release"],
                "controlled_release_discharge_m3s": 75,
            },
        )
        assert generated.status_code == 201, generated.text
        payload = generated.json()
        assert payload["base_scenario_id"] == scenario_id
        assert payload["generator_version"] == "1.0"
        assert [item["code"] for item in payload["variants"]] == [
            "partial_breach",
            "major_breach",
            "extreme_breach",
            "controlled_release",
        ]
        assert payload["variants"][0]["parameters"]["breach_width_m"] == 10
        assert payload["variants"][3]["parameters"]["controlled_release_discharge_m3s"] == 75

        listed = client.get(
            f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants"
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()) == 4

        duplicate = client.post(
            f"/api/v1/projects/{project_id}/scenarios/{scenario_id}/variants/generate",
            json={"presets": ["major_breach"]},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "CONFLICT"
    finally:
        client.close()
        engine.dispose()


def test_generate_variants_rejects_wrong_project(tmp_path):
    client, engine = make_client(tmp_path)
    try:
        project_a = client.post("/api/v1/projects", json={"name": "A"}).json()["id"]
        project_b = client.post("/api/v1/projects", json={"name": "B"}).json()["id"]
        scenario = client.post(
            f"/api/v1/projects/{project_a}/scenarios",
            json=valid_base_scenario(),
        ).json()["id"]
        response = client.post(
            f"/api/v1/projects/{project_b}/scenarios/{scenario}/variants/generate",
            json={"presets": ["partial_breach"]},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    finally:
        client.close()
        engine.dispose()
