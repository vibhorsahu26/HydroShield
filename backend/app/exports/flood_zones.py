from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape


ZONE_DEFINITIONS = (
    (0, 0.5, "Shallow", "#38bdf8"),
    (0.5, 1.0, "Moderate", "#22c55e"),
    (1.0, 2.0, "Deep", "#f59e0b"),
    (2.0, None, "Very deep", "#dc2626"),
)


def _zone_for_depth(value: float, flood_threshold_m: float) -> int:
    if value <= flood_threshold_m:
        return 0
    for index, (_low, high, _label, _color) in enumerate(ZONE_DEFINITIONS, start=1):
        if high is None or value <= high:
            return index
    return len(ZONE_DEFINITIONS)


def build_flood_zones(source_path: str | Path, *, flood_threshold_m: float = 0.05) -> dict[str, Any]:
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Water-depth raster does not exist: {path}")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("Water-depth raster has no CRS.")
        values = src.read(1, masked=True).filled(np.nan).astype("float64")
        finite = np.isfinite(values)
        flooded = finite & (values > flood_threshold_m)
        if not flooded.any():
            return {
                "type": "FeatureCollection",
                "features": [],
                "bbox": None,
                "zones": [
                    {"id": i + 1, "label": label, "min_m": max(float(low), float(flood_threshold_m)), "max_m": high, "color": color}
                    for i, (low, high, label, color) in enumerate(ZONE_DEFINITIONS)
                ],
            }

        classified = np.zeros(values.shape, dtype="uint8")
        for row, col in zip(*np.where(flooded)):
            classified[row, col] = _zone_for_depth(float(values[row, col]), flood_threshold_m)

        records: list[dict[str, Any]] = []
        geometries = []
        for geom_mapping, zone_index in shapes(classified, mask=classified > 0, transform=src.transform, connectivity=8):
            polygon = shape(geom_mapping)
            if polygon.is_empty or polygon.area <= 0:
                continue
            zone_low, zone_high, label, color = ZONE_DEFINITIONS[int(zone_index) - 1]
            zone_mask = (classified == zone_index)
            cells = int(np.count_nonzero(zone_mask))
            records.append({
                "zone_id": int(len(records) + 1),
                "zone": label,
                "depth_min_m": float(max(zone_low, flood_threshold_m)),
                "depth_max_m": float(zone_high) if zone_high is not None else float(np.nanmax(values[zone_mask])),
                "area_km2": float(polygon.area / 1_000_000.0),
                "cell_count": cells,
                "color": color,
            })
            geometries.append(polygon)

        gdf = gpd.GeoDataFrame(records, geometry=geometries, crs=src.crs).to_crs("EPSG:4326")
        features = []
        for row in gdf.itertuples(index=False):
            properties = {
                "zone_id": int(row.zone_id),
                "zone": row.zone,
                "depth_min_m": float(row.depth_min_m),
                "depth_max_m": float(row.depth_max_m),
                "area_km2": float(row.area_km2),
                "cell_count": int(row.cell_count),
                "color": row.color,
            }
            features.append({
                "type": "Feature",
                "properties": properties,
                "geometry": row.geometry.__geo_interface__,
            })

        minx, miny, maxx, maxy = gdf.total_bounds.tolist()
        return {
            "type": "FeatureCollection",
            "features": features,
            "bbox": [[float(miny), float(minx)], [float(maxy), float(maxx)]],
            "zones": [
                {
                    "id": i + 1,
                    "label": label,
                    "min_m": float(max(low, flood_threshold_m)),
                    "max_m": float(high) if high is not None else None,
                    "color": color,
                }
                for i, (low, high, label, color) in enumerate(ZONE_DEFINITIONS)
            ],
        }
