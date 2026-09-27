from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping

from app.analysis.exposure import analyze_exposure
from app.analysis.raster_metrics import (
    align_to_reference,
    continuous_metrics,
    flood_mask,
    inundated_area_m2,
    polygon_from_mask,
    read_single_band,
    write_float_raster,
    write_mask_raster,
)


DISCHARGE_COLUMNS = {"q", "discharge", "discharge_m3s", "flow", "flow_m3s", "outflow", "outflow_m3s"}


def _max_from_csv(path: str | Path) -> float | None:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Discharge CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Discharge CSV has no header.")
        lookup = {name.strip().lower(): name for name in reader.fieldnames}
        column = next((lookup[c] for c in DISCHARGE_COLUMNS if c in lookup), None)
        if column is None:
            raise ValueError("Discharge CSV has no recognized discharge column.")
        values: list[float] = []
        for row in reader:
            try:
                values.append(float(row[column]))
            except (TypeError, ValueError):
                continue
    return max(values) if values else None


def process_result(
    *,
    water_depth_raster: str,
    velocity_raster: str | None,
    arrival_time_raster: str | None,
    water_level_raster: str | None,
    dem_raster: str | None,
    discharge_csv: str | None,
    flood_threshold_m: float,
    output_dir: Path,
    exposure_layers: dict[str, str],
) -> dict[str, Any]:
    depth = read_single_band(water_depth_raster, name="water depth")
    finite_depth = depth.array[np.isfinite(depth.array)]
    if finite_depth.size == 0:
        raise ValueError("Water-depth raster contains no finite values.")
    if np.any(finite_depth < 0):
        raise ValueError("Water-depth raster contains negative depth values.")
    mask = flood_mask(depth, flood_threshold_m)
    output_dir.mkdir(parents=True, exist_ok=True)

    flood_mask_path = output_dir / "flood_mask.tif"
    write_mask_raster(flood_mask_path, mask, depth)
    flood_polygon = polygon_from_mask(mask, depth.transform)
    polygon_path = output_dir / "flood_extent.geojson"
    if flood_polygon is not None:
        gpd.GeoDataFrame(
            {"flooded": [1]},
            geometry=[flood_polygon],
            crs=depth.crs,
        ).to_file(polygon_path, driver="GeoJSON")
    else:
        gpd.GeoDataFrame({"flooded": []}, geometry=[], crs=depth.crs).to_file(polygon_path, driver="GeoJSON")

    inundated_area = inundated_area_m2(mask, depth.transform)
    metrics: dict[str, Any] = {
        "flood_threshold_m": flood_threshold_m,
        "max_water_depth_m": float(np_nanmax(depth.array)),
        "inundated_area_m2": inundated_area,
        "inundated_area_km2": inundated_area / 1_000_000.0,
        "flooded_cell_count": int(mask.sum()),
    }
    warnings: list[str] = []

    velocity_path = None
    if velocity_raster:
        velocity = read_single_band(velocity_raster, name="velocity")
        values = align_to_reference(velocity, depth)
        finite = values[np.isfinite(values)]
        if finite.size:
            metrics["max_velocity_mps"] = float(finite.max())
        velocity_path = output_dir / "velocity_aligned.tif"
        write_float_raster(velocity_path, values, depth)

    arrival_path = None
    if arrival_time_raster:
        arrival = read_single_band(arrival_time_raster, name="arrival time")
        values = align_to_reference(arrival, depth)
        finite_wet = values[mask & np.isfinite(values)]
        metrics["first_arrival_time_s"] = float(finite_wet.min()) if finite_wet.size else None
        arrival_path = output_dir / "arrival_time_aligned.tif"
        write_float_raster(arrival_path, values, depth)
    else:
        metrics["first_arrival_time_s"] = None
        warnings.append("No arrival-time raster was supplied; first-arrival time was omitted.")

    max_water_level_path = None
    if water_level_raster:
        level = read_single_band(water_level_raster, name="water level")
        values = align_to_reference(level, depth)
        finite = values[np.isfinite(values)]
        if finite.size:
            metrics["max_water_level_m"] = float(finite.max())
        max_water_level_path = output_dir / "water_level_aligned.tif"
        write_float_raster(max_water_level_path, values, depth)
    elif dem_raster:
        dem = read_single_band(dem_raster, name="DEM")
        dem_values = align_to_reference(dem, depth)
        valid = np.isfinite(dem_values) & np.isfinite(depth.array)
        if np.any(valid):
            level = np.where(valid, dem_values + depth.array, np.nan)
            metrics["max_water_level_m"] = float(np_nanmax(level))
            max_water_level_path = output_dir / "water_level_derived.tif"
            write_float_raster(max_water_level_path, level, depth)
    else:
        metrics["max_water_level_m"] = None
        warnings.append("No water-level raster or DEM was supplied; maximum water level was omitted.")

    if discharge_csv:
        metrics["max_discharge_m3s"] = _max_from_csv(discharge_csv)
    else:
        metrics["max_discharge_m3s"] = None
        warnings.append("No discharge CSV was supplied; maximum discharge was omitted.")

    exposure = {"exposed_area_m2": metrics["inundated_area_m2"], "layers": {}}
    if flood_polygon is not None and exposure_layers:
        exposure, exposure_warnings = analyze_exposure(flood_polygon, flood_crs=depth.crs, layers=exposure_layers)
        warnings.extend(exposure_warnings)

    artifacts = {
        "water_depth_raster": str(Path(water_depth_raster).resolve()),
        "flood_mask_raster": str(flood_mask_path.resolve()),
        "flood_extent_geojson": str(polygon_path.resolve()),
    }
    if velocity_path:
        artifacts["velocity_raster"] = str(velocity_path.resolve())
    if arrival_path:
        artifacts["arrival_time_raster"] = str(arrival_path.resolve())
    if max_water_level_path:
        artifacts["water_level_raster"] = str(max_water_level_path.resolve())
    return {"metrics": metrics, "exposure": exposure, "artifacts": artifacts, "warnings": warnings}


def np_nanmax(values):
    import numpy as np

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("Water-depth raster contains no finite elevation/depth cells.")
    return np.max(finite)
