from __future__ import annotations

import io

import geopandas as gpd
import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from shapely.geometry import LineString

from app.main import create_app


def make_dem():
    transform = from_origin(77.00, 28.12, 0.0015, 0.0015)
    values = np.ones((80, 80), dtype=np.float32) * 100
    profile = {
        "driver": "GTiff",
        "width": 80,
        "height": 80,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
    }
    buf = io.BytesIO()
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(values, 1)
    return buf.getvalue()


def make_river():
    gdf = gpd.GeoDataFrame(
        {"name": ["Demo River"]},
        geometry=[LineString([(77.02, 28.045), (77.10, 28.045)])],
        crs="EPSG:4326",
    )
    return gdf.to_json().encode()


def test_geospatial_endpoint_integrates_phase2_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_PROCESSING_WORK_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/geospatial/preprocess",
        data={"resolution_m": "500", "river_buffer_m": "1000"},
        files={
            "dem": ("demo.tif", make_dem(), "image/tiff"),
            "river": ("river.geojson", make_river(), "application/geo+json"),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["processing_crs"].startswith("EPSG:326")
    assert payload["dem"]["valid_cell_count"] > 0
    assert payload["river"]["feature_count"] >= 1
    assert payload["domain"]["area_m2"] > 1


def test_geospatial_endpoint_rejects_invalid_river_via_phase2_validator(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_PROCESSING_WORK_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    client = TestClient(create_app())
    bad_river = gpd.GeoDataFrame(
        {"name": ["not-a-river"]},
        geometry=[__import__("shapely").geometry.Point(77.05, 28.05)],
        crs="EPSG:4326",
    ).to_json().encode()
    response = client.post(
        "/api/v1/geospatial/preprocess",
        files={
            "dem": ("demo.tif", make_dem(), "image/tiff"),
            "river": ("river.geojson", bad_river, "application/geo+json"),
        },
    )
    assert response.status_code == 400
    assert "River validation failed" in response.json()["detail"]
