from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Project, Scenario, ScenarioVariant, SimulationJob
from app.database.session import get_db
from app.main import create_app
from fastapi.testclient import TestClient


def write_depth(path, value):
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32",
                       crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=-9999) as dst:
        dst.write(np.full((2, 2), value, dtype="float32"), 1)


def test_analyze_simulation_result_endpoint(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="API Analysis Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    depth = tmp_path / "depth.tif"; write_depth(depth, 0.5)
    db.close()

    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.post(f"/api/v1/results/simulations/{job.id}/analyze", json={"water_depth_raster": str(depth), "flood_threshold_m": 0.05})
        assert response.status_code == 201
        payload = response.json()
        assert payload["metrics"]["inundated_area_m2"] == 400.0
        assert payload["analysis_version"] == "phase8-v1"
    engine.dispose()


def test_process_native_sph_result_endpoint(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'native-api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Native API Analysis Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)

    dem = tmp_path / "dem.tif"
    write_depth(dem, 100.0)
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"
    particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("x;y;z;vx;vy;vz\n5;15;101;0;3;0\n", encoding="utf-8")
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={"preprocessed_dem": str(dem), "sph_output_interval_s": 1}, working_directory=str(work), cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    db.close()

    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.post(f"/api/v1/results/simulations/{job.id}/process-native", json={"flood_threshold_m": 0.05})
        assert response.status_code == 201
        payload = response.json()
        assert payload["analysis_version"] == "phase8-native-sph-v1"
        assert payload["metrics"]["max_water_depth_m"] == 1.0
        assert payload["metrics"]["max_velocity_mps"] == 3.0
        assert payload["artifacts"]["water_depth_raster"].endswith("water_depth_max.tif")
    engine.dispose()


def test_process_native_sph_result_endpoint_returns_actionable_422_on_processing_error(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'native-error-api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Native Error API Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    db.close()

    def boom(*args, **kwargs):
        raise ValueError("test-native-processing-failure")

    monkeypatch.setattr("app.api.routes.results.service.analyze_native_sph_job", boom)
    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.post(f"/api/v1/results/simulations/{job.id}/process-native", json={"flood_threshold_m": 0.05})
        assert response.status_code == 422
        assert "test-native-processing-failure" in response.json()["detail"]
    engine.dispose()


def test_process_native_result_endpoint_retries_failed_postprocessing_job(tmp_path):
    from datetime import datetime, timezone
    engine = create_engine(f"sqlite:///{tmp_path / 'native-retry-api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Native Retry API Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    dem = tmp_path / "dem.tif"; write_depth(dem, 100.0)
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"; particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("x;y;z;vx;vy;vz\n5;15;101;0;3;0\n", encoding="utf-8")
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="failed", progress=99, current_step="result_processing_failed", attempt=1, max_attempts=1, timeout_s=10, config={"preprocessed_dem": str(dem), "sph_output_interval_s": 1}, working_directory=str(work), cancel_requested=False, result={"postprocessing":{"status":"failed","error":"old"}}, error_message="old", finished_at=datetime.now(timezone.utc))
    db.add(job); db.commit(); db.refresh(job); db.close()

    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.post(f"/api/v1/results/simulations/{job.id}/process-native", json={"flood_threshold_m": 0.05, "force": True})
        assert response.status_code == 201
        assert response.json()["metrics"]["max_water_depth_m"] == 1.0
        session = SessionLocal()
        try:
            refreshed = session.get(SimulationJob, job.id)
            assert refreshed.status == "completed"
            assert refreshed.current_step == "complete"
        finally:
            session.close()
    engine.dispose()


def test_sample_analysis_raster_returns_geographic_value_and_units(tmp_path):
    from app.database.models import AnalysisResult
    engine = create_engine(f"sqlite:///{tmp_path / 'sample-api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Sample Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    depth = tmp_path / "depth.tif"
    write_depth(depth, 2.5)
    record = AnalysisResult(simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={}, artifacts={"water_depth_raster": str(depth)}, warnings=[], assumptions={})
    db.add(record); db.commit(); db.refresh(record)
    db.close()
    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(5, 15)
        response = client.get(f"/api/v1/exports/analysis/{record.id}/sample", params={"artifact": "water_depth_raster", "latitude": lat, "longitude": lon})
        assert response.status_code == 200
        payload = response.json()
        assert payload["inside"] is True
        assert payload["value"] == 2.5
        assert payload["unit"] == "m"
        preview = client.get(f"/api/v1/exports/analysis/{record.id}/preview", params={"artifact": "water_depth_raster"})
        assert preview.status_code == 200
        assert preview.json()["metadata"]["label"] == "Water Depth"
        assert preview.json()["metadata"]["unit"] == "m"
    engine.dispose()


def test_arrival_time_sample_and_preview_use_minutes(tmp_path):
    from app.database.models import AnalysisResult
    engine = create_engine(f"sqlite:///{tmp_path / 'arrival-sample.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Arrival Sample Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    arrival = tmp_path / "arrival.tif"
    with rasterio.open(arrival, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32", crs="EPSG:32643", transform=from_origin(0, 20, 10, 10), nodata=-9999) as dst:
        dst.write(np.full((2, 2), 1200.0, dtype="float32"), 1)
    record = AnalysisResult(simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, analysis_version="phase8-v1", flood_threshold_m=0.05, metrics={}, exposure={}, artifacts={"arrival_time_raster": str(arrival)}, warnings=[], assumptions={})
    db.add(record); db.commit(); db.refresh(record); db.close()
    app = create_app()
    def override_db():
        session = SessionLocal()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        from pyproj import Transformer
        lon, lat = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform(5, 15)
        sampled = client.get(f"/api/v1/exports/analysis/{record.id}/sample", params={"artifact":"arrival_time_raster","latitude":lat,"longitude":lon})
        assert sampled.status_code == 200
        assert sampled.json()["value"] == 20.0
        assert sampled.json()["unit"] == "min"
        preview = client.get(f"/api/v1/exports/analysis/{record.id}/preview", params={"artifact":"arrival_time_raster"})
        assert preview.status_code == 200
        assert preview.json()["metadata"]["min_value"] == 20.0
        assert preview.json()["metadata"]["max_value"] == 20.0
    engine.dispose()


def test_demo_analysis_api_populates_missing_exposure_categories(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    engine = create_engine(f"sqlite:///{tmp_path / 'demo-exposure-api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Demo Exposure API Project"); db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="A", model="sph", config={}); db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="v1", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={}); db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    depth = tmp_path / "depth.tif"; write_depth(depth, 0.5)
    db.close()

    app = create_app()
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.post(f"/api/v1/results/simulations/{job.id}/analyze", json={"water_depth_raster": str(depth), "flood_threshold_m": 0.05})
        assert response.status_code == 201
        exposure = response.json()["exposure"]
        assert set(["settlement", "road", "bridge", "critical_infrastructure"]).issubset(exposure["layers"])
        assert all(exposure["layers"][key].get("fallback") is True for key in ["settlement", "road", "bridge", "critical_infrastructure"])
        assert set(exposure["presentation"]["fallback_categories"]) == {"settlement", "road", "bridge", "critical_infrastructure"}
    engine.dispose()
