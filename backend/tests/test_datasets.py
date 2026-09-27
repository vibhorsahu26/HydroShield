import io
import json

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin


def make_dem_geotiff() -> bytes:
    buffer = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": 3,
        "width": 3,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(77.0, 29.0, 0.01, 0.01),
    }
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dataset:
            dataset.write(
                np.array(
                    [[100.0, 101.0, 102.0], [99.0, 100.0, 101.0], [98.0, 99.0, 100.0]],
                    dtype="float32",
                ),
                1,
            )
        buffer.write(memfile.read())
    return buffer.getvalue()


def river_geojson() -> bytes:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Demo River"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[77.0, 29.0], [77.1, 28.95]],
                },
            }
        ],
    }
    return json.dumps(payload).encode()


def test_dem_geotiff_is_accepted(client):
    response = client.post(
        "/api/v1/datasets/validate",
        data={"dataset_type": "dem"},
        files={"file": ("demo_dem.tif", make_dem_geotiff(), "image/tiff")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["format"] == "GeoTIFF"
    assert body["crs"] == "EPSG:4326"
    assert body["shape"] == [1, 3, 3]


def test_river_geojson_is_accepted(client):
    response = client.post(
        "/api/v1/datasets/validate",
        data={"dataset_type": "river"},
        files={"file": ("river.geojson", river_geojson(), "application/geo+json")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["geometry_types"] == ["LineString"]
    assert body["feature_count"] == 1


def test_river_rejects_polygon_geometry(client):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77, 29], [77.1, 29], [77.1, 28.9], [77, 29]]],
                },
            }
        ],
    }
    response = client.post(
        "/api/v1/datasets/validate",
        data={"dataset_type": "river"},
        files={"file": ("bad.geojson", json.dumps(payload).encode(), "application/geo+json")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("Geometry types" in error for error in body["errors"])


def test_invalid_extension_returns_400(client):
    response = client.post(
        "/api/v1/datasets/validate",
        data={"dataset_type": "dem"},
        files={"file": ("notes.txt", b"not geospatial", "text/plain")},
    )
    assert response.status_code == 400
