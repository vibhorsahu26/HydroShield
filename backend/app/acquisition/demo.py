from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, Polygon, mapping

from app.acquisition.schemas import DamCandidate


DEMO_CRS = "EPSG:32643"
DEMO_CENTER_LAT = 28.8312653382
DEMO_CENTER_LON = 77.0395865173
DEMO_WIDTH = 180
DEMO_HEIGHT = 180
DEMO_RESOLUTION_M = 100.0
DEMO_ORIGIN_X = 690000.0
DEMO_ORIGIN_Y = 3200000.0
DEMO_RIVER_NAME = "HydroShield River"


def demo_candidate(query: str) -> DamCandidate:
    label = query.strip() or "HydroShield Dam"
    lower = label.lower()
    river_by_name = {
        "narmada": "Narmada River",
        "tehri": "Bhagirathi River",
        "bhakra": "Sutlej River",
        "hirakud": "Mahanadi River",
        "sardar sarovar": "Narmada River",
        "ukaim": "Tapi River",
        "nagarjuna": "Krishna River",
        "srisailam": "Krishna River",
        "tungabhadra": "Tungabhadra River",
        "koyna": "Koyna River",
        "almatti": "Krishna River",
        "ukaim": "Tapi River",
    }
    river_name = next((river for key, river in river_by_name.items() if key in lower), None)
    return DamCandidate(
        display_name=label,
        name=label,
        latitude=DEMO_CENTER_LAT,
        longitude=DEMO_CENTER_LON,
        osm_type=None,
        osm_id=None,
        category="dam",
        object_type="dam",
        river_name=river_name,
    )


def _write_raster(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": int(array.shape[0]),
        "width": int(array.shape[1]),
        "count": 1,
        "dtype": "float32",
        "crs": DEMO_CRS,
        "transform": from_origin(DEMO_ORIGIN_X, DEMO_ORIGIN_Y, DEMO_RESOLUTION_M, DEMO_RESOLUTION_M),
        "nodata": -9999.0,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)


def _geojson(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "HydroShield Prototype Study Data",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def _feature(geometry, **properties: Any) -> dict[str, Any]:
    return {"type": "Feature", "properties": properties, "geometry": mapping(geometry)}


def _write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_geojson(features), separators=(",", ":")), encoding="utf-8")


def _utm_to_lonlat(x: float, y: float) -> tuple[float, float]:
    # This fixed transformation avoids adding a runtime dependency beyond pyproj,
    # which is already used by the geospatial pipeline.
    from pyproj import Transformer

    transformer = Transformer.from_crs(DEMO_CRS, "EPSG:4326", always_xy=True)
    return transformer.transform(x, y)


def _river_features(river_name: str) -> list[dict[str, Any]]:
    pts = []
    for i in range(13):
        x = DEMO_ORIGIN_X + 1500 + i * 1300
        y = DEMO_ORIGIN_Y - 3500 - i * 660 + 450 * math.sin(i / 2.2)
        pts.append(_utm_to_lonlat(x, y))
    return [_feature(LineString(pts), name=river_name, waterway="river", prototype=True)]


def _point_feature(x: float, y: float, **properties: Any) -> dict[str, Any]:
    lon, lat = _utm_to_lonlat(x, y)
    return _feature(Point(lon, lat), **properties)


def _line_feature(points: list[tuple[float, float]], **properties: Any) -> dict[str, Any]:
    lonlat = [_utm_to_lonlat(x, y) for x, y in points]
    return _feature(LineString(lonlat), **properties)


def _polygon_feature(cx: float, cy: float, half_size: float, **properties: Any) -> dict[str, Any]:
    corners = [
        _utm_to_lonlat(cx - half_size, cy - half_size),
        _utm_to_lonlat(cx + half_size, cy - half_size),
        _utm_to_lonlat(cx + half_size, cy + half_size),
        _utm_to_lonlat(cx - half_size, cy + half_size),
        _utm_to_lonlat(cx - half_size, cy - half_size),
    ]
    return _feature(Polygon(corners), **properties)


def generate_demo_acquisition(
    run_dir: Path,
    *,
    dam_name: str,
    river_name: str | None = None,
) -> dict[str, Any]:
    """Generate a self-contained study package for offline prototype runs.

    The package is deliberately written in the same formats/CRS conventions as
    the real acquisition path so the normal validation, preprocessing, mapping,
    exposure and export pipelines can consume it without a frontend mock.
    """
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    river_name = river_name or DEMO_RIVER_NAME

    y, x = np.mgrid[0:DEMO_HEIGHT, 0:DEMO_WIDTH]
    cx, cy = DEMO_WIDTH * 0.40, DEMO_HEIGHT * 0.54
    distance = np.sqrt(((x - cx) * 0.9) ** 2 + (y - cy) ** 2)
    channel = np.exp(-((y - (cy + 0.17 * (x - cx))) ** 2) / (2 * 18.0**2))
    dem = 112.0 + 0.028 * x + 0.022 * y + 4.0 * np.sin(x / 27.0) * np.cos(y / 35.0)
    dem -= 6.0 * channel

    dem_path = run_dir / "dem.tif"
    _write_raster(dem_path, dem)

    river_path = run_dir / "river.geojson"
    river_features = _river_features(river_name)
    _write_geojson(river_path, river_features)

    # Dam location is close to the upstream end of the synthetic river and is
    # intentionally colocated with the browser-visible prototype result grid.
    dam_x = DEMO_ORIGIN_X + 6900
    dam_y = DEMO_ORIGIN_Y - 10600
    dam_path = run_dir / "dam.geojson"
    _write_geojson(
        dam_path,
        [_point_feature(dam_x, dam_y, name=dam_name, type="dam", prototype=True)],
    )

    # Exposure layers are simple but spatially distributed so the normal exposure
    # service can produce non-empty counts when the flood footprint intersects them.
    settlement_points = [
        (DEMO_ORIGIN_X + 7800, DEMO_ORIGIN_Y - 11500),
        (DEMO_ORIGIN_X + 9500, DEMO_ORIGIN_Y - 12800),
        (DEMO_ORIGIN_X + 10800, DEMO_ORIGIN_Y - 9600),
        (DEMO_ORIGIN_X + 12500, DEMO_ORIGIN_Y - 14500),
    ]
    settlement_path = run_dir / "settlement.geojson"
    _write_geojson(
        settlement_path,
        [_point_feature(x, y, name=f"Settlement {i + 1}", place="village", prototype=True) for i, (x, y) in enumerate(settlement_points)],
    )

    road_path = run_dir / "road.geojson"
    road_lines = [
        [
            (DEMO_ORIGIN_X + 2500, DEMO_ORIGIN_Y - 7500),
            (DEMO_ORIGIN_X + 7000, DEMO_ORIGIN_Y - 10300),
            (DEMO_ORIGIN_X + 11500, DEMO_ORIGIN_Y - 13200),
            (DEMO_ORIGIN_X + 15500, DEMO_ORIGIN_Y - 15700),
        ],
        [
            (DEMO_ORIGIN_X + 5200, DEMO_ORIGIN_Y - 4500),
            (DEMO_ORIGIN_X + 8200, DEMO_ORIGIN_Y - 8200),
            (DEMO_ORIGIN_X + 14500, DEMO_ORIGIN_Y - 11400),
        ],
    ]
    _write_geojson(road_path, [_line_feature(points, highway="secondary", name=f"Prototype Road {i + 1}", prototype=True) for i, points in enumerate(road_lines)])

    building_path = run_dir / "building.geojson"
    buildings = []
    for i, (bx, by) in enumerate(
        [
            (DEMO_ORIGIN_X + 7000, DEMO_ORIGIN_Y - 11000),
            (DEMO_ORIGIN_X + 7600, DEMO_ORIGIN_Y - 11400),
            (DEMO_ORIGIN_X + 8200, DEMO_ORIGIN_Y - 11800),
            (DEMO_ORIGIN_X + 9400, DEMO_ORIGIN_Y - 12500),
            (DEMO_ORIGIN_X + 10100, DEMO_ORIGIN_Y - 13000),
            (DEMO_ORIGIN_X + 11000, DEMO_ORIGIN_Y - 13600),
            (DEMO_ORIGIN_X + 12400, DEMO_ORIGIN_Y - 14600),
            (DEMO_ORIGIN_X + 13700, DEMO_ORIGIN_Y - 15100),
        ]
    ):
        buildings.append(_polygon_feature(bx, by, 90, building=f"B-{i + 1:02d}", prototype=True))
    _write_geojson(building_path, buildings)

    bridge_path = run_dir / "bridge.geojson"
    _write_geojson(
        bridge_path,
        [
            _point_feature(DEMO_ORIGIN_X + 8900, DEMO_ORIGIN_Y - 12100, highway="bridge", name="Bridge 1", prototype=True),
            _point_feature(DEMO_ORIGIN_X + 11900, DEMO_ORIGIN_Y - 13900, highway="bridge", name="Bridge 2", prototype=True),
        ],
    )

    critical_path = run_dir / "critical_infrastructure.geojson"
    _write_geojson(
        critical_path,
        [
            _point_feature(DEMO_ORIGIN_X + 9300, DEMO_ORIGIN_Y - 12600, amenity="hospital", name="District Hospital", prototype=True),
            _point_feature(DEMO_ORIGIN_X + 11600, DEMO_ORIGIN_Y - 14100, amenity="fire_station", name="Emergency Services", prototype=True),
        ],
    )

    files = {
        "dem": dem_path,
        "river": river_path,
        "dam": dam_path,
        "settlement": settlement_path,
        "road": road_path,
        "building": building_path,
        "bridge": bridge_path,
        "critical_infrastructure": critical_path,
    }
    sources = {}
    for key, path in files.items():
        data = path.read_bytes()
        sources[key] = {"size_bytes": len(data), "checksum_sha256": sha256(data).hexdigest()}

    return {
        "paths": files,
        "sources": sources,
        "bbox_wgs84": [
            DEMO_CENTER_LON - 0.12,
            DEMO_CENTER_LAT - 0.09,
            DEMO_CENTER_LON + 0.12,
            DEMO_CENTER_LAT + 0.09,
        ],
        "center": {"latitude": DEMO_CENTER_LAT, "longitude": DEMO_CENTER_LON},
        "river_name": river_name,
    }
