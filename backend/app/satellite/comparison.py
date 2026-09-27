from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import reproject, Resampling
import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union


def _read_mask(path: str | Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        arr = src.read(1).astype("float64")
        profile = src.profile.copy()
        nodata = src.nodata
        if nodata is not None:
            valid = np.isfinite(arr) & (arr != nodata)
        else:
            valid = np.isfinite(arr)
        return arr, {"profile": profile, "transform": src.transform, "crs": src.crs, "valid": valid}


def _reproject_mask(source: np.ndarray, source_meta: dict, reference_meta: dict) -> np.ndarray:
    source_valid = source_meta["valid"] & np.isfinite(source)
    prepared_source = np.where(source_valid, source, -9999.0).astype("float64")
    destination = np.full(reference_meta["shape"], -9999.0, dtype="float64")
    reproject(
        source=prepared_source,
        destination=destination,
        src_transform=source_meta["transform"],
        src_crs=source_meta["crs"],
        src_nodata=-9999.0,
        dst_transform=reference_meta["transform"],
        dst_crs=reference_meta["crs"],
        dst_nodata=-9999.0,
        resampling=Resampling.nearest,
    )
    return destination


def _write_float(path: Path, data: np.ndarray, meta: dict) -> None:
    profile = meta["profile"].copy()
    profile.update(count=1, dtype="float32", nodata=-9999.0, compress="deflate")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype("float32"), 1)


def _write_extent_geojson(path: Path, mask: np.ndarray, meta: dict) -> None:
    geoms = []
    for geom, value in shapes(mask.astype("uint8"), mask=mask.astype(bool), transform=meta["transform"]):
        if value == 1:
            geoms.append(shape(geom))
    path.parent.mkdir(parents=True, exist_ok=True)
    if geoms:
        dissolved = unary_union(geoms)
        gdf = gpd.GeoDataFrame({"water": [1]}, geometry=[dissolved], crs=meta["crs"])
    else:
        gdf = gpd.GeoDataFrame({"water": []}, geometry=[], crs=meta["crs"])
    gdf.to_file(path, driver="GeoJSON")


def compare_predicted_observed(*, model_mask_path: str, observed_mask_path: str, output_dir: Path) -> dict[str, Any]:
    model_arr, model_meta = _read_mask(model_mask_path)
    obs_arr, obs_meta = _read_mask(observed_mask_path)
    if model_meta["crs"] is None or obs_meta["crs"] is None:
        raise ValueError("Both model and satellite masks require a CRS.")
    if model_meta["crs"].is_geographic:
        raise ValueError("Model flood mask must use a projected CRS for area agreement metrics.")

    reference_meta = dict(model_meta)
    reference_meta["shape"] = model_arr.shape
    obs_on_model = _reproject_mask(obs_arr, obs_meta, reference_meta)

    model_valid = model_meta["valid"] & np.isfinite(model_arr)
    obs_valid = obs_on_model != -9999.0
    comparable = model_valid & obs_valid
    if not comparable.any():
        raise ValueError("Model and satellite masks have no overlapping valid pixels.")

    model_water = model_arr > 0.5
    observed_water = obs_on_model > 0.5
    intersection = model_water & observed_water & comparable
    model_only = model_water & ~observed_water & comparable
    observed_only = observed_water & ~model_water & comparable
    union = (model_water | observed_water) & comparable

    pixel_area = abs(float(model_meta["transform"].a * model_meta["transform"].e))
    model_count = int((model_water & comparable).sum())
    observed_count = int((observed_water & comparable).sum())
    intersection_count = int(intersection.sum())
    union_count = int(union.sum())
    model_only_count = int(model_only.sum())
    observed_only_count = int(observed_only.sum())

    metrics = {
        "model_area_m2": model_count * pixel_area,
        "observed_area_m2": observed_count * pixel_area,
        "intersection_area_m2": intersection_count * pixel_area,
        "union_area_m2": union_count * pixel_area,
        "model_only_area_m2": model_only_count * pixel_area,
        "observed_only_area_m2": observed_only_count * pixel_area,
        "iou": intersection_count / union_count if union_count else 1.0,
        "precision": intersection_count / model_count if model_count else None,
        "recall": intersection_count / observed_count if observed_count else None,
        "f1": (2 * intersection_count / (model_count + observed_count)) if (model_count + observed_count) else 1.0,
        "comparable_area_m2": int(comparable.sum()) * pixel_area,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    diff = np.full(model_arr.shape, np.nan, dtype="float64")
    diff[intersection] = 0
    diff[model_only] = -1
    diff[observed_only] = 1
    diff_path = output_dir / "satellite_difference.tif"
    _write_float(diff_path, diff, model_meta)
    observed_extent = output_dir / "observed_flood_extent.geojson"
    _write_extent_geojson(observed_extent, observed_water & comparable, model_meta)

    return {
        "metrics": metrics,
        "observed_extent_path": str(observed_extent.resolve()),
        "difference_map_path": str(diff_path.resolve()),
        "artifacts": {
            "observed_mask_raster": str(Path(observed_mask_path).resolve()),
            "observed_flood_extent": str(observed_extent.resolve()),
            "difference_map": str(diff_path.resolve()),
        },
    }
