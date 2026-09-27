from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from app.analysis.raster_metrics import (
    RasterData,
    align_to_reference,
    continuous_metrics,
    flood_comparison_metrics,
    flood_mask,
    read_single_band,
    write_float_raster,
)


def _common_reference(left: RasterData, right: RasterData) -> RasterData:
    """Build a common projected grid covering the spatial union of both rasters."""
    if left.crs is None or right.crs is None:
        raise ValueError("Both comparison rasters must have a CRS.")
    right_bounds = transform_bounds(right.crs, left.crs, *right_bounds_tuple(right), densify_pts=21)
    left_bounds = right_bounds_tuple(left)
    minx = min(left_bounds[0], right_bounds[0])
    miny = min(left_bounds[1], right_bounds[1])
    maxx = max(left_bounds[2], right_bounds[2])
    maxy = max(left_bounds[3], right_bounds[3])
    res_x = abs(float(left.transform.a))
    res_y = abs(float(left.transform.e))
    width = max(1, int(np.ceil((maxx - minx) / res_x)))
    height = max(1, int(np.ceil((maxy - miny) / res_y)))
    transform = from_origin(minx, maxy, res_x, res_y)
    array = np.full((height, width), np.nan, dtype="float64")
    return RasterData(Path("<common-comparison-grid>"), array, left.crs, transform, np.nan)


def right_bounds_tuple(raster: RasterData) -> tuple[float, float, float, float]:
    left = float(raster.transform.c)
    top = float(raster.transform.f)
    right = left + raster.width * float(raster.transform.a)
    bottom = top + raster.height * float(raster.transform.e)
    return (min(left, right), min(bottom, top), max(left, right), max(bottom, top))


def compare_analysis_artifacts(
    *,
    left_depth_path: str,
    right_depth_path: str,
    left_velocity_path: str | None,
    right_velocity_path: str | None,
    left_arrival_path: str | None,
    right_arrival_path: str | None,
    flood_threshold_m: float,
    output_dir: Path,
) -> dict[str, Any]:
    left_depth = read_single_band(left_depth_path, name="left water depth")
    right_depth = read_single_band(right_depth_path, name="right water depth")
    if left_depth.crs.is_geographic or right_depth.crs.is_geographic:
        raise ValueError("Comparison requires projected analysis rasters.")

    reference = _common_reference(left_depth, right_depth)
    left_depth_values = align_to_reference(left_depth, reference)
    right_depth_values = align_to_reference(right_depth, reference)
    output_dir.mkdir(parents=True, exist_ok=True)

    depth_diff = right_depth_values - left_depth_values
    depth_diff[~(np.isfinite(left_depth_values) & np.isfinite(right_depth_values))] = np.nan
    depth_diff_path = output_dir / "depth_difference.tif"
    write_float_raster(depth_diff_path, depth_diff, reference)

    left_mask = np.isfinite(left_depth_values) & (left_depth_values > flood_threshold_m)
    right_mask = np.isfinite(right_depth_values) & (right_depth_values > flood_threshold_m)
    flood_metrics = flood_comparison_metrics(left_mask, right_mask, reference.transform)
    flood_difference = right_mask.astype(float) - left_mask.astype(float)
    flood_difference_path = output_dir / "flood_difference.tif"
    write_float_raster(flood_difference_path, flood_difference, reference)

    metrics: dict[str, Any] = {
        "flood": flood_metrics,
        "depth": continuous_metrics(left_depth_values, right_depth_values),
    }
    artifacts = {
        "depth_difference_raster": str(depth_diff_path.resolve()),
        "flood_difference_raster": str(flood_difference_path.resolve()),
    }

    def compare_optional(left_path: str | None, right_path: str | None, key: str):
        if not left_path or not right_path:
            return
        left = read_single_band(left_path, name=f"left {key}")
        right = read_single_band(right_path, name=f"right {key}")
        left_values = align_to_reference(left, reference)
        right_values = align_to_reference(right, reference)
        metrics[key] = continuous_metrics(left_values, right_values)
        diff = right_values - left_values
        diff[~(np.isfinite(left_values) & np.isfinite(right_values))] = np.nan
        path = output_dir / f"{key}_difference.tif"
        write_float_raster(path, diff, reference)
        artifacts[f"{key}_difference_raster"] = str(path.resolve())

    compare_optional(left_velocity_path, right_velocity_path, "velocity")
    compare_optional(left_arrival_path, right_arrival_path, "arrival_time")
    return {"metrics": metrics, "artifacts": artifacts, "warnings": []}
