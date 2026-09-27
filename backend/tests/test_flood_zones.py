from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.exports.flood_zones import build_flood_zones


def write_depth(path: Path, data: np.ndarray) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(0, 40, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(data.astype("float32"), 1)


def test_flood_zones_returns_hoverable_depth_bands(tmp_path: Path):
    path = tmp_path / "depth.tif"
    data = np.array(
        [
            [0.0, 0.2, 0.7, 1.4],
            [0.0, 0.4, 1.2, 2.4],
            [0.0, 0.0, 0.0, 0.0],
            [0.6, 0.9, 2.1, 2.8],
        ],
        dtype=float,
    )
    write_depth(path, data)
    payload = build_flood_zones(path, flood_threshold_m=0.05)
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]
    zones = {feature["properties"]["zone"] for feature in payload["features"]}
    assert {"Shallow", "Moderate", "Deep", "Very deep"}.issubset(zones)
    first = payload["features"][0]["properties"]
    assert first["area_km2"] > 0
    assert first["cell_count"] >= 1
    assert first["color"].startswith("#")
    assert len(payload["bbox"]) == 2


def test_flood_zones_empty_when_nothing_exceeds_threshold(tmp_path: Path):
    path = tmp_path / "dry.tif"
    write_depth(path, np.zeros((3, 3), dtype=float))
    payload = build_flood_zones(path, flood_threshold_m=0.05)
    assert payload["features"] == []
    assert payload["bbox"] is None
