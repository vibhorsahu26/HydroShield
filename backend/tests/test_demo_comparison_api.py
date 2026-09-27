import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant
from app.database.session import get_db
from app.api.routes.simulations import get_job_manager
from app.orchestration.states import JobStatus


class FakeManager:
    def __init__(self):
        self.last_job = None

    def create_and_submit(self, db, *, project_id, scenario_id, variant_id, model, prepare, max_attempts):
        from app.database.models import SimulationJob
        from datetime import datetime, timezone
        job = SimulationJob(
            project_id=project_id, scenario_id=scenario_id, variant_id=variant_id, model=model.value,
            status=JobStatus.QUEUED.value, progress=0.0, current_step="queued", attempt=0, max_attempts=max_attempts,
            timeout_s=prepare.timeout_s, config=prepare.model_dump(mode="json"), cancel_requested=False,
            queued_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        db.add(job); db.commit(); db.refresh(job); self.last_job = job
        return job


@pytest.fixture()
def comparison_client(tmp_path, monkeypatch):
    db_path = tmp_path / "comparison-demo.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    from app.main import create_app
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    manager = FakeManager()
    app.dependency_overrides[get_job_manager] = lambda: manager

    db = SessionLocal()
    project = Project(name="Prototype comparison")
    db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(
        project_id=project.id, name="Prototype study", model="sph",
        config={"name":"Prototype study","initial_reservoir_water_level_m":100.0,"reservoir_volume_m3":1000000.0,"breach_width_m":50.0,"breach_depth_m":10.0,"breach_formation_time_s":600.0,"initial_discharge_m3s":250.0,"simulation_duration_s":3600.0,"model":"sph"},
    )
    db.add(scenario); db.commit(); db.refresh(scenario)
    source_variant = ScenarioVariant(base_scenario_id=scenario.id, code="partial_breach", kind="dam_breach", preset="Partial Breach", breach_fraction=0.25, model="sph", parameters={"release_mode":"dam_breach","model":"sph","initial_reservoir_water_level_m":100.0,"reservoir_volume_m3":1000000.0,"breach_width_m":12.5,"breach_depth_m":2.5,"breach_formation_time_s":600.0,"initial_discharge_m3s":62.5,"simulation_duration_s":3600.0}, assumptions={})
    db.add(source_variant); db.commit(); db.refresh(source_variant)
    from app.database.models import SimulationJob
    from datetime import datetime, timezone
    source_job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=source_variant.id, model="sph", status="completed", progress=100.0, current_step="complete", attempt=1, max_attempts=1, timeout_s=3600.0, config={"timeout_s":3600.0,"sph_device":"cpu"}, cancel_requested=False, created_at=datetime.now(timezone.utc), queued_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(source_job); db.commit(); db.refresh(source_job)
    source = AnalysisResult(simulation_job_id=source_job.id, project_id=project.id, scenario_id=scenario.id, variant_id=source_variant.id, analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={}, artifacts={"water_depth_raster":"x"}, warnings=[], assumptions={})
    db.add(source); db.commit(); db.refresh(source)
    source_id = source.id
    db.close()

    with TestClient(app) as client:
        yield client, source_id, manager
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def test_demo_comparison_creates_second_variant_and_job(comparison_client):
    client, source_id, manager = comparison_client
    response = client.post("/api/v1/results/comparison-demo", json={"source_analysis_id": source_id})
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["model"] == "sph"
    assert payload["prototype"] is True
    assert payload["comparison_variant_code"] != "partial_breach"
    assert manager.last_job is not None
    assert manager.last_job.variant_id == payload["comparison_variant_id"]


def test_demo_comparison_disabled_outside_demo_mode(comparison_client, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "false")
    get_settings.cache_clear()
    client, source_id, _ = comparison_client
    response = client.post("/api/v1/results/comparison-demo", json={"source_analysis_id": source_id})
    assert response.status_code == 409
    get_settings.cache_clear()
