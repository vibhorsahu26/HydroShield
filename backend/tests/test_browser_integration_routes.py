from io import BytesIO
from zipfile import ZipFile

import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.database.base import Base
from app.database.session import build_session_factory, get_db
from app.main import create_app


def _dem_bytes():
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(77.0, 29.0, 0.01, 0.01),
        "nodata": -9999,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            import numpy as np
            ds.write(np.ones((2, 2), dtype="float32"), 1)
        return mem.read()


def _river_bytes():
    return b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"LineString","coordinates":[[77.0,29.0],[77.02,28.98]]}}],"crs":{"type":"name","properties":{"name":"EPSG:4326"}}}'


def _model_zip():
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("Case_Def.xml", "<case><execution><parameters><parameter key=\"TimeMax\" value=\"1\" /></parameters></execution></case>")
    return buf.getvalue()


def test_model_input_upload_bridge(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bridge.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = build_session_factory(engine)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    client = TestClient(app)
    project = client.post("/api/v1/projects", json={"name": "Bridge Project"}).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/model-inputs",
        data={"model": "sph"},
        files={"file": ("case.zip", _model_zip(), "application/zip")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["native_input_directory"]
    assert "Case_Def.xml" in payload["files"]
    app.dependency_overrides.clear()
    engine.dispose()


def test_analysis_input_upload_bridge_requires_completed_job(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-input.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = build_session_factory(engine)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    client = TestClient(app)
    response = client.post(
        "/api/v1/results/simulations/not-a-job/analysis-inputs",
        files={"water_depth_raster": ("depth.tif", _dem_bytes(), "image/tiff")},
    )
    assert response.status_code == 404
    app.dependency_overrides.clear()
    engine.dispose()
