import json
from pathlib import Path

from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import mapping, Point
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Project
from app.database.session import get_db
from app.main import create_app


def make_client(tmp_path, monkeypatch):
    from app.core.config import Settings
    settings = Settings(
        environment="development",
        database_url=f"sqlite:///{tmp_path / 'preview.db'}",
        storage_root=tmp_path / "uploads",
        processing_work_dir=tmp_path / "processed",
        export_root=tmp_path / "exports",
        model_work_dir=tmp_path / "models",
    )
    monkeypatch.setattr("app.api.routes.dataset_previews.get_settings", lambda: settings)
    engine = create_engine(settings.database_url, poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    return TestClient(app), engine, SessionLocal, settings


def test_vector_dataset_preview_returns_wgs84_geojson(tmp_path, monkeypatch):
    client, engine, SessionLocal, settings = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    project = Project(name="Preview Project")
    db.add(project)
    db.commit()
    db.refresh(project)
    path = settings.storage_root / project.id / "dam.geojson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Dam"},
            "geometry": mapping(Point(85.0, 28.0)),
        }],
    }), encoding="utf-8")
    from app.database.repositories.datasets import DatasetRepository
    record = DatasetRepository().create(
        db,
        project_id=project.id,
        dataset_type="dam",
        filename=path.name,
        storage_uri=str(path.resolve()),
        format="GeoJSON",
        validation_status="validated",
        crs="EPSG:4326",
        geometry_types=["Point"],
        shape=None,
        bounds=[85.0, 28.0, 85.0, 28.0],
        feature_count=1,
        columns=["name"],
        warnings=[],
        errors=[],
    )
    db.close()
    response = client.get(f"/api/v1/projects/{project.id}/datasets/{record.id}/preview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["geometry"]["type"] == "Point"
    engine.dispose()



def test_vector_dataset_preview_serializes_datetime_properties(tmp_path, monkeypatch):
    client, engine, SessionLocal, settings = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    project = Project(name="Datetime Preview Project")
    db.add(project)
    db.commit()
    db.refresh(project)
    path = settings.storage_root / project.id / "dam.geojson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Dam", "observed_at": "2026-09-22T12:00:00"},
            "geometry": mapping(Point(85.0, 28.0)),
        }],
    }), encoding="utf-8")
    from app.database.repositories.datasets import DatasetRepository
    record = DatasetRepository().create(
        db, project_id=project.id, dataset_type="dam", filename=path.name, storage_uri=str(path.resolve()),
        format="GeoJSON", validation_status="validated", crs="EPSG:4326", geometry_types=["Point"],
        shape=None, bounds=[85.0, 28.0, 85.0, 28.0], feature_count=1, columns=["name", "observed_at"], warnings=[], errors=[]
    )
    db.close()
    # Rewrite via geopandas would normally materialize a pandas Timestamp; the endpoint must still serialize it.
    import geopandas as gpd
    gdf = gpd.read_file(path)
    gdf["observed_at"] = __import__("pandas").to_datetime(gdf["observed_at"])
    gdf.to_file(path, driver="GeoJSON")
    response = client.get(f"/api/v1/projects/{project.id}/datasets/{record.id}/preview")
    assert response.status_code == 200, response.text
    assert response.json()["features"][0]["properties"]["observed_at"]
    engine.dispose()


def test_vector_dataset_preview_rejects_other_project_and_raster(tmp_path, monkeypatch):
    client, engine, SessionLocal, settings = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    project = Project(name="Preview Project")
    other = Project(name="Other Project")
    db.add_all([project, other])
    db.commit()
    db.refresh(project); db.refresh(other)
    raster = settings.storage_root / project.id / "dem.tif"
    raster.parent.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "GTiff", "width": 2, "height": 2, "count": 1, "dtype": "float32", "crs": "EPSG:4326", "transform": from_origin(85, 28, .1, .1)}
    import numpy as np
    with MemoryFile() as mem:
        with mem.open(**profile) as src:
            src.write(np.ones((2,2), dtype="float32"), 1)
        raster.write_bytes(mem.read())
    from app.database.repositories.datasets import DatasetRepository
    dem = DatasetRepository().create(db, project_id=project.id, dataset_type="dem", filename="dem.tif", storage_uri=str(raster.resolve()), format="GeoTIFF", validation_status="validated", crs="EPSG:4326", geometry_types=[], shape=[1,2,2], bounds=[84.9,27.8,85,28], feature_count=None, columns=[], warnings=[], errors=[])
    db.close()
    assert client.get(f"/api/v1/projects/{other.id}/datasets/{dem.id}/preview").status_code == 404
    assert client.get(f"/api/v1/projects/{project.id}/datasets/{dem.id}/preview").status_code == 400
    engine.dispose()


def test_raster_dataset_preview_returns_bounds_and_image_path(tmp_path, monkeypatch):
    client, engine, SessionLocal, settings = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    project = Project(name="Raster Preview Project")
    db.add(project); db.commit(); db.refresh(project)
    raster_path = settings.storage_root / project.id / "dem.tif"
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    import numpy as np
    profile = {"driver": "GTiff", "width": 4, "height": 4, "count": 1, "dtype": "float32", "crs": "EPSG:32643", "transform": from_origin(500000, 3000000, 30, 30), "nodata": -9999}
    with rasterio.open(raster_path, "w", **profile) as dst:
        dst.write(np.arange(16, dtype="float32").reshape(4, 4), 1)
    from app.database.repositories.datasets import DatasetRepository
    record = DatasetRepository().create(
        db, project_id=project.id, dataset_type="dem", filename="dem.tif", storage_uri=str(raster_path.resolve()),
        format="GeoTIFF", validation_status="validated", crs="EPSG:32643", geometry_types=[], shape=[1, 4, 4],
        bounds=[500000, 2999880, 500120, 3000000], feature_count=None, columns=[], warnings=[], errors=[]
    )
    db.close()
    response = client.get(f"/api/v1/projects/{project.id}/datasets/{record.id}/raster-preview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataset_type"] == "dem"
    assert len(body["bounds"]) == 2
    assert body["image_path"].endswith("/raster-preview/image")
    image = client.get(f"/api/v1/projects/{project.id}/datasets/{record.id}/raster-preview/image")
    assert image.status_code == 200, image.text
    assert image.headers["content-type"].startswith("image/png")
    engine.dispose()
