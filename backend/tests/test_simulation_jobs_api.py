from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.session import get_db
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.main import create_app
from app.modelling.base import ExecutionResult, ModelAdapter, PreparedModel
from app.orchestration.manager import SimulationJobManager
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
from app.schemas.scenarios import ScenarioConfig
from app.scenarios.generator import generate_scenario_variants

from tests.test_orchestration import FakeModellingService, valid_base


def make_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api_jobs.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    manager.modelling = FakeModellingService("success")
    app.state.job_manager = manager
    return TestClient(app), engine, manager


def setup_project(client: TestClient):
    project = client.post("/api/v1/projects", json={"name": "API Job Project"}).json()
    scenario = client.post(f"/api/v1/projects/{project['id']}/scenarios", json=valid_base().model_dump(mode="json"))
    assert scenario.status_code == 201, scenario.text
    scenario_id = scenario.json()["id"]
    # Use Phase 5 public API, not direct DB setup, to prove integration.
    variants = client.post(
        f"/api/v1/projects/{project['id']}/scenarios/{scenario_id}/variants/generate",
        json={"presets": ["major_breach"]},
    )
    assert variants.status_code == 201, variants.text
    listed = client.get(f"/api/v1/projects/{project["id"]}/scenarios/{scenario_id}/variants")
    assert listed.status_code == 200
    variant_id = listed.json()[0]["id"]
    return project["id"], scenario_id, variant_id


def request_payload(tmp_path):
    native = tmp_path / "native"
    native.mkdir(exist_ok=True)
    (native / "Case_Def.xml").write_text("<case/>", encoding="utf-8")
    return {
        "native_input_directory": str(native),
        "working_directory": str(tmp_path / "run"),
        "sph_device": "cpu",
        "timeout_s": 10,
    }


def wait_terminal(client: TestClient, job_id: str):
    deadline = time.time() + 5
    while time.time() < deadline:
        response = client.get(f"/api/v1/simulations/{job_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("simulation did not finish")


def test_simulation_job_api_queues_and_completes(tmp_path):
    client, engine, manager = make_client(tmp_path)
    try:
        project_id, scenario_id, variant_id = setup_project(client)
        response = client.post(
            "/api/v1/simulations",
            json={
                "project_id": project_id,
                "scenario_id": scenario_id,
                "variant_id": variant_id,
                "model": "sph",
                "prepare": request_payload(tmp_path),
                "max_attempts": 1,
            },
        )
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["status"] in {"queued", "preparing", "running", "processing", "completed"}
        final = wait_terminal(client, job["id"])
        assert final["status"] == "completed"
        assert final["progress"] == 100.0
        listed = client.get(f"/api/v1/simulations/projects/{project_id}")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == job["id"]
    finally:
        manager.shutdown(wait=True)
        client.close(); engine.dispose()


def test_simulation_job_api_rejects_variant_from_other_scenario(tmp_path):
    client, engine, manager = make_client(tmp_path)
    try:
        project_id, scenario_id, variant_id = setup_project(client)
        other = client.post(f"/api/v1/projects/{project_id}/scenarios", json={**valid_base().model_dump(mode="json"), "name": "Other"}).json()["id"]
        response = client.post(
            "/api/v1/simulations",
            json={
                "project_id": project_id,
                "scenario_id": other,
                "variant_id": variant_id,
                "model": "sph",
                "prepare": request_payload(tmp_path),
            },
        )
        assert response.status_code == 404
    finally:
        manager.shutdown(wait=True); client.close(); engine.dispose()


def test_simulation_list_rejects_missing_project(tmp_path):
    client, engine, manager = make_client(tmp_path)
    try:
        response = client.get('/api/v1/simulations/projects/not-a-project')
        assert response.status_code == 404
    finally:
        manager.shutdown(wait=True); client.close(); engine.dispose()
