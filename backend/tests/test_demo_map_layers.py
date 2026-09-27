from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.database.base import Base
from app.database.models import Project
from app.database.session import get_db
from app.main import create_app


def test_demo_acquisition_map_layers_have_browser_previews(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    settings.storage_root = tmp_path / "uploads"
    settings.processing_work_dir = tmp_path / "processed"
    settings.export_root = tmp_path / "exports"

    engine = create_engine(f"sqlite:///{tmp_path / 'map.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()

    db = SessionLocal()
    project = Project(name="Map Layer Project")
    db.add(project); db.commit(); db.refresh(project)
    project_id = project.id
    db.close()

    client = TestClient(app)
    response = client.post(
        f"/api/v1/acquisition/projects/{project_id}/run",
        json={
            "dam_name": "Prototype Dam",
            "latitude": 28.8312653382,
            "longitude": 77.0395865173,
            "radius_km": 10,
            "river_name": "Prototype River",
            "include_exposure": True,
            "auto_preprocess": True,
        },
    )
    assert response.status_code == 201, response.text
    datasets = response.json()["datasets"]

    by_logical = {item["logical_type"]: item["dataset_id"] for item in datasets}
    expected_vectors = {"river", "dam", "settlement", "road", "building", "bridge", "critical_infrastructure"}
    assert expected_vectors.issubset(by_logical)
    assert "dem" in by_logical

    for logical_type in sorted(expected_vectors):
        preview = client.get(f"/api/v1/projects/{project_id}/datasets/{by_logical[logical_type]}/preview?logical_type={logical_type}")
        assert preview.status_code == 200, (logical_type, preview.text)
        body = preview.json()
        assert body["type"] == "FeatureCollection"
        assert body["features"]

    raster_preview = client.get(f"/api/v1/projects/{project_id}/datasets/{by_logical['dem']}/raster-preview")
    assert raster_preview.status_code == 200, raster_preview.text
    assert raster_preview.json()["bounds"]

    image_path = settings.export_root / "dataset-previews" / project_id / by_logical["dem"] / "preview.png"
    assert Path(image_path).is_file()
    engine.dispose()
    get_settings.cache_clear()
