from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


EXPOSURE_LAYER_NAMES = ("settlement", "road", "bridge", "critical_infrastructure")


def read_exposure_layer(path: str | Path, name: str) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Exposure layer '{name}' does not exist: {path}")
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:
        raise ValueError(f"Exposure layer '{name}' could not be read: {exc}") from exc
    if gdf.empty:
        return gdf
    if gdf.crs is None:
        raise ValueError(f"Exposure layer '{name}' has no CRS.")
    return gdf


def _intersection_measure(geometries: gpd.GeoSeries, *, layer_crs) -> tuple[float, str]:
    if geometries.empty:
        return 0.0, "count"
    geom_types = set(geometries.geom_type.dropna())
    if geom_types and geom_types.issubset({"LineString", "MultiLineString"}):
        return float(geometries.length.sum() / 1000.0), "length_km"
    if geom_types and geom_types.issubset({"Polygon", "MultiPolygon"}):
        return float(geometries.area.sum()), "area_m2"
    return float(len(geometries)), "count"


def analyze_exposure(
    flood_geometry: BaseGeometry,
    *,
    flood_crs,
    layers: dict[str, str],
) -> tuple[dict[str, Any], list[str]]:
    if flood_geometry is None or flood_geometry.is_empty:
        return {"exposed_area_m2": 0.0, "layers": {}}, []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "exposed_area_m2": float(flood_geometry.area),
        "layers": {},
    }
    for name, path in layers.items():
        gdf = read_exposure_layer(path, name)
        if gdf.empty:
            summary["layers"][name] = {"affected_count": 0}
            continue
        projected = gdf.to_crs(flood_crs)
        intersections = projected[projected.geometry.intersects(flood_geometry)].copy()
        clipped = intersections.geometry.intersection(flood_geometry)
        measure, unit = _intersection_measure(clipped, layer_crs=flood_crs)
        layer_summary: dict[str, Any] = {"affected_count": int(len(intersections)), unit: measure}
        if name.lower() in {"settlements", "settlement"}:
            layer_summary["category"] = "settlement"
        elif name.lower() in {"roads", "road"}:
            layer_summary["category"] = "road"
        elif name.lower() in {"bridges", "bridge"}:
            layer_summary["category"] = "bridge"
        elif name.lower() in {"critical_infrastructure", "infrastructure"}:
            layer_summary["category"] = "critical_infrastructure"
        else:
            layer_summary["category"] = "other"
        summary["layers"][name] = layer_summary
    return summary, warnings


def build_demo_exposure_fallback(exposed_area_m2: float) -> dict[str, Any]:
    """Return deterministic prototype exposure values for missing source layers.

    This is intentionally a small, stable presentation fallback for demo mode only.
    It is not a population model and should not be interpreted as an official impact
    estimate. The caller records the fallback in persisted assumptions.
    """
    area_km2 = max(float(exposed_area_m2 or 0.0), 0.0) / 1_000_000.0
    settlements = min(24, max(1, int(round(area_km2 * 0.08)))) if area_km2 > 0 else 0
    roads_km = min(40.0, round(area_km2 * 0.12, 2))
    bridges = min(8, max(1, int(round(area_km2 * 0.018)))) if area_km2 > 0 else 0
    critical = min(8, max(1, int(round(area_km2 * 0.015)))) if area_km2 > 0 else 0
    return {
        "settlement": {"affected_count": settlements, "category": "settlement", "fallback": True},
        "road": {"affected_count": 0 if roads_km == 0 else max(1, int(round(roads_km / 2.5))), "intersected_length_km": roads_km, "category": "road", "fallback": True},
        "bridge": {"affected_count": bridges, "category": "bridge", "fallback": True},
        "critical_infrastructure": {"affected_count": critical, "category": "critical_infrastructure", "fallback": True},
    }


def complete_demo_exposure(exposure: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    """Fill missing prototype exposure categories without replacing real intersections."""
    if not enabled:
        return exposure
    result = dict(exposure or {})
    layers = dict(result.get("layers") or {})
    category_aliases = {
        "settlement": "settlement", "settlements": "settlement",
        "road": "road", "roads": "road",
        "bridge": "bridge", "bridges": "bridge",
        "critical_infrastructure": "critical_infrastructure", "infrastructure": "critical_infrastructure",
    }
    existing_categories = set()
    for key, data in layers.items():
        canonical = str((data or {}).get("category") or category_aliases.get(str(key).lower()) or key).lower()
        if canonical in EXPOSURE_LAYER_NAMES:
            existing_categories.add(canonical)
    fallbacks = build_demo_exposure_fallback(float(result.get("exposed_area_m2") or 0.0))
    for key, fallback in fallbacks.items():
        if key not in existing_categories:
            layers[key] = fallback
    result["layers"] = layers
    fallback_categories = []
    coverage = {}
    for key in EXPOSURE_LAYER_NAMES:
        matching = [data for layer_key, data in layers.items() if str((data or {}).get("category") or category_aliases.get(str(layer_key).lower()) or layer_key).lower() == key]
        is_fallback = any((data or {}).get("fallback") is True for data in matching) and key not in existing_categories
        fallback_categories.append(key) if is_fallback else None
        coverage[key] = not is_fallback and bool(matching)
    result["presentation"] = {
        "coverage": coverage,
        "fallback_categories": fallback_categories,
    }
    return result
