from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Project, Scenario, ScenarioVariant, SimulationJob
from app.database.session import get_db
from app.main import create_app
from app.modelling.demo import generate_demo_case


def test_demo_timeline_api_serves_time_indexed_frames(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    settings.model_work_dir = tmp_path / "model"
    settings.export_root = tmp_path / "exports"

    engine = create_engine(f"sqlite:///{tmp_path / 'timeline.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()

    db = SessionLocal()
    project = Project(name="Timeline Project")
    db.add(project)
    db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="Timeline Scenario", model="sph", config={})
    db.add(scenario)
    db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(
        base_scenario_id=scenario.id,
        code="major_breach",
        kind="dam_breach",
        preset="Major Breach",
        model="sph",
        parameters={"simulation_duration_s": 3600},
        assumptions={},
    )
    db.add(variant)
    db.commit(); db.refresh(variant)

    generated = generate_demo_case(settings.model_work_dir / "jobs" / "timeline", variant_parameters={"simulation_duration_s": 3600})
    job = SimulationJob(
        project_id=project.id,
        scenario_id=scenario.id,
        variant_id=variant.id,
        model="sph",
        status="completed",
        progress=100,
        current_step="complete",
        attempt=1,
        max_attempts=1,
        timeout_s=3600,
        config={},
        working_directory=generated["working_directory"],
        manifest_path=generated["manifest_path"],
        cancel_requested=False,
        result={"execution_mode": "prototype", "artifacts": generated["time_series_water_depth"]},
    )
    db.add(job)
    db.commit(); db.refresh(job)
    job_id = job.id
    db.close()

    client = TestClient(app)
    response = client.get(f"/api/v1/results/simulations/{job_id}/timeline")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert len(payload["frames"]) == 6
    assert payload["frames"][0]["time_s"] < payload["frames"][-1]["time_s"]
    assert payload["frames"][0]["bounds"]
    assert payload["frames"][0]["metadata"]["unit"] == "m"

    image = client.get(f"/api/v1/results/simulations/{job_id}/timeline/image?frame=0")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert len(image.content) > 100

    missing = client.get(f"/api/v1/results/simulations/{job_id}/timeline/image?frame=99")
    assert missing.status_code == 404

    engine.dispose()
    get_settings.cache_clear()


def test_demo_simulation_to_timeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    settings.model_work_dir = tmp_path / "model"
    settings.export_root = tmp_path / "exports"

    engine = create_engine(f"sqlite:///{tmp_path / 'e2e.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()

    from app.orchestration.manager import SimulationJobManager
    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    app.state.job_manager = manager

    client = TestClient(app)
    try:
        project = client.post("/api/v1/projects", json={"name": "Timeline E2E"}).json()
        scenario_body = {
            "name": "Timeline scenario",
            "initial_reservoir_water_level_m": 120,
            "reservoir_volume_m3": 5_000_000,
            "breach_width_m": 50,
            "breach_depth_m": 20,
            "breach_formation_time_s": 1800,
            "initial_discharge_m3s": 0,
            "simulation_duration_s": 3600,
            "model": "sph",
        }
        scenario_response = client.post(f"/api/v1/projects/{project['id']}/scenarios", json=scenario_body)
        assert scenario_response.status_code == 201, scenario_response.text
        scenario = scenario_response.json()
        variants_response = client.post(
            f"/api/v1/projects/{project['id']}/scenarios/{scenario['id']}/variants/generate",
            json={"presets": ["major_breach"]},
        )
        assert variants_response.status_code == 201, variants_response.text
        variant = client.get(f"/api/v1/projects/{project['id']}/scenarios/{scenario['id']}/variants").json()[0]

        response = client.post(
            "/api/v1/simulations",
            json={
                "project_id": project["id"],
                "scenario_id": scenario["id"],
                "variant_id": variant["id"],
                "model": "sph",
                "prepare": {
                    "native_input_directory": str(tmp_path / "native"),
                    "working_directory": str(tmp_path / "run"),
                    "sph_device": "cpu",
                    "timeout_s": 30,
                },
                "max_attempts": 1,
            },
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]

        import time
        deadline = time.time() + 5
        final = None
        while time.time() < deadline:
            final = client.get(f"/api/v1/simulations/{job_id}").json()
            if final["status"] == "completed":
                break
            time.sleep(0.05)
        assert final["status"] == "completed"

        timeline = client.get(f"/api/v1/results/simulations/{job_id}/timeline").json()
        assert timeline["available"] is True
        assert len(timeline["frames"]) == 6
        image = client.get(f"/api/v1/results/simulations/{job_id}/timeline/image?frame=3")
        assert image.status_code == 200
        assert image.content[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        manager.shutdown(wait=True)
        client.close()
        engine.dispose()
        get_settings.cache_clear()
