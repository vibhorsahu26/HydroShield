import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.acquisition.manager import AcquisitionManager
from app.acquisition.overpass import OverpassClient
from app.acquisition.schemas import AutomaticAcquisitionRequest
from app.core.config import Settings
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.services.geospatial_service import GeospatialService


def dem_bytes():
    profile = {
        "driver": "GTiff", "height": 20, "width": 20, "count": 1, "dtype": "float32",
        "crs": "EPSG:4326", "transform": from_origin(85.0, 28.2, 0.01, 0.01), "nodata": -9999,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            ds.write(np.linspace(10, 30, 400, dtype="float32").reshape(20, 20), 1)
        return mem.read()


def test_automatic_acquisition_full_chain(monkeypatch, tmp_path):
    settings = Settings(
        environment="development",
        database_url=f"sqlite:///{tmp_path / 'auto_e2e.db'}",
        storage_root=tmp_path / "uploads",
        processing_work_dir=tmp_path / "processed",
        export_root=tmp_path / "exports",
        model_work_dir=tmp_path / "models",
        max_acquisition_download_bytes=20 * 1024 * 1024,
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    from app.database.models import Project
    project = Project(name="Automatic E2E")
    db.add(project); db.commit(); db.refresh(project)

    manager = AcquisitionManager(settings)

    class FakeDem:
        def fetch(self, bbox, cache_dir, output_path, resolution):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(dem_bytes())
            return {"resolution": "90m", "tile_count": 1, "source": "Fake Copernicus GLO-90"}

    payload = {"elements": [
        {"type": "way", "id": 1, "tags": {"waterway": "river", "name": "Test River"}, "geometry": [{"lat": 28.05, "lon": 85.02}, {"lat": 28.15, "lon": 85.15}]},
        {"type": "node", "id": 2, "tags": {"man_made": "dam", "name": "Test Dam"}, "lat": 28.10, "lon": 85.10},
        {"type": "way", "id": 3, "tags": {"highway": "primary"}, "geometry": [{"lat": 28.08, "lon": 85.05}, {"lat": 28.18, "lon": 85.12}]},
        {"type": "node", "id": 4, "tags": {"place": "village", "name": "Test Village"}, "lat": 28.12, "lon": 85.12},
    ]}

    manager.dem = FakeDem()
    manager.overpass = type("FakeOverpass", (), {
        "fetch": lambda self, request: payload,
        "split_layers": lambda self, p, dam_point, river_name=None: OverpassClient().split_layers(p, dam_point=dam_point, river_name=river_name),
    })()
    manager.geospatial = GeospatialService()

    request = AutomaticAcquisitionRequest(
        dam_name="Test Dam", latitude=28.1, longitude=85.1, radius_km=5,
        river_name="Test River", dem_resolution="90m", include_exposure=True, auto_preprocess=True,
    )
    run, acquired, preprocessing, warnings, bbox = manager.run(db, project.id, request)
    assert run.status == "completed"
    assert preprocessing and Path(preprocessing["dem"]["path"]).exists()
    assert Path(preprocessing["river"]["path"]).exists()
    assert Path(preprocessing["domain"]["path"]).exists()
    assert Path(preprocessing["domain"]["mask_raster_path"]).exists()
    db.refresh(run)
    assert run.provider_summary["bbox_wgs84"] == list(bbox)
    assert run.provider_summary["preprocessing"]["dem"]["path"] == preprocessing["dem"]["path"]
    assert "© OpenStreetMap contributors" in run.provider_summary["osm_attribution"]
    logical = {item["logical_type"] for item in acquired}
    assert {"dem", "river", "dam", "settlement", "road"}.issubset(logical)
    db.close(); engine.dispose()
