from fastapi.testclient import TestClient
from shapely.geometry import Point
from shapely import to_wkb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.repositories.spatial_features import SpatialFeatureRepository
from app.database.session import get_db
from app.main import create_app
from tests.test_datasets import make_dem_geotiff


def make_client(tmp_path):
    db_path = tmp_path / "phase3.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
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
    return TestClient(app), SessionLocal, engine


def valid_scenario():
    return {
        "name": "Major Breach",
        "initial_reservoir_water_level_m": 120,
        "reservoir_volume_m3": 5_000_000,
        "breach_width_m": 30,
        "breach_depth_m": 15,
        "breach_formation_time_s": 300,
        "initial_discharge_m3s": 100,
        "simulation_duration_s": 3600,
        "model": "both",
    }


def test_project_dataset_and_scenario_persistence_integrates_with_validation(tmp_path):
    client, _, engine = make_client(tmp_path)
    try:
        project_response = client.post("/api/v1/projects", json={"name": "Test Basin"})
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]

        validation_response = client.post(
            "/api/v1/datasets/validate",
            data={"dataset_type": "dem"},
            files={"file": ("demo_dem.tif", make_dem_geotiff(), "image/tiff")},
        )
        assert validation_response.status_code == 200, validation_response.text
        validated = validation_response.json()
        assert validated["valid"] is True

        dataset_response = client.post(
            f"/api/v1/projects/{project_id}/datasets",
            json={
                "dataset_type": validated["dataset_type"],
                "filename": validated["filename"],
                "storage_uri": "local://datasets/demo_dem.tif",
                "format": validated["format"],
                "validation_status": "validated" if validated["valid"] else "rejected",
                "crs": validated["crs"],
                "geometry_types": validated["geometry_types"],
                "shape": validated["shape"],
                "bounds": validated["bounds"],
                "feature_count": validated["feature_count"],
                "columns": validated["columns"],
                "warnings": validated["warnings"],
                "errors": validated["errors"],
            },
        )
        assert dataset_response.status_code == 201, dataset_response.text

        scenario_validation = client.post("/api/v1/scenarios/validate", json=valid_scenario())
        assert scenario_validation.status_code == 200, scenario_validation.text

        scenario_response = client.post(
            f"/api/v1/projects/{project_id}/scenarios",
            json=valid_scenario(),
        )
        assert scenario_response.status_code == 201, scenario_response.text
        assert scenario_response.json()["config"]["breach_depth_m"] == 15

        datasets = client.get(f"/api/v1/projects/{project_id}/datasets")
        assert datasets.status_code == 200
        assert len(datasets.json()) == 1

        scenarios = client.get(f"/api/v1/projects/{project_id}/scenarios")
        assert scenarios.status_code == 200
        assert len(scenarios.json()) == 1
    finally:
        client.close()
        engine.dispose()


def test_missing_project_is_rejected(tmp_path):
    client, _, engine = make_client(tmp_path)
    try:
        response = client.post(
            "/api/v1/projects/missing/scenarios",
            json=valid_scenario(),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    finally:
        client.close()
        engine.dispose()


def test_spatial_feature_bbox_query_with_same_repository_contract(tmp_path):
    _, SessionLocal, engine = make_client(tmp_path)
    db = SessionLocal()
    try:
        from app.database.models import Project

        project = Project(name="Spatial Test")
        db.add(project)
        db.commit()
        db.refresh(project)

        repo = SpatialFeatureRepository()
        inside = repo.create(
            db,
            project_id=project.id,
            dataset_id=None,
            feature_type="settlement",
            geometry_wkb=to_wkb(Point(77.05, 28.05)),
            geometry_srid=4326,
            properties={"name": "Inside"},
        )
        repo.create(
            db,
            project_id=project.id,
            dataset_id=None,
            feature_type="settlement",
            geometry_wkb=to_wkb(Point(78.0, 29.0)),
            geometry_srid=4326,
            properties={"name": "Outside"},
        )

        matches = repo.intersects_bbox(
            db,
            project_id=project.id,
            bbox=(77.0, 28.0, 77.1, 28.1),
            srid=4326,
        )
        assert len(matches) == 1
        assert matches[0].id == inside.id
    finally:
        db.close()
        engine.dispose()
