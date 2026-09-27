from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt, gaussian_filter


DEMO_CRS = "EPSG:32643"
DEMO_WIDTH = 180
DEMO_HEIGHT = 180
DEMO_RESOLUTION_M = 100.0
DEMO_ORIGIN_X = 690000.0
DEMO_ORIGIN_Y = 3200000.0


def _write_raster(path: Path, array: np.ndarray, *, profile: dict[str, Any] | None = None, nodata: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if profile is None:
        profile = {
            "driver": "GTiff",
            "height": array.shape[0],
            "width": array.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": DEMO_CRS,
            "transform": from_origin(DEMO_ORIGIN_X, DEMO_ORIGIN_Y, DEMO_RESOLUTION_M, DEMO_RESOLUTION_M),
            "compress": "deflate",
        }
    else:
        profile = dict(profile)
        profile.update(driver="GTiff", height=array.shape[0], width=array.shape[1], count=1, dtype="float32", compress="deflate")
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.asarray(array, dtype="float32"), 1)


def _write_timeseries(directory: Path, depth: np.ndarray, profile: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    # Six distinct snapshots are enough for a clear browser playback while
    # keeping payload size small. The easing curve makes early propagation and
    # later filling visibly different without requiring a longer simulation.
    fractions = (0.03, 0.13, 0.30, 0.52, 0.76, 1.0)
    directory.mkdir(parents=True, exist_ok=True)
    for index, fraction in enumerate(fractions):
        path = directory / f"water_depth_t{index:04d}.tif"
        _write_raster(path, depth * fraction, profile=profile)
        paths.append(str(path.resolve()))
    return paths


def _variant_signature(variant_parameters: dict[str, Any] | None) -> tuple[float, int]:
    parameters = variant_parameters or {}
    release_mode = str(parameters.get("release_mode") or "dam_breach")
    if release_mode == "controlled_release":
        release = float(parameters.get("controlled_release_discharge_m3s") or 250.0)
        severity = float(np.clip(0.55 + 0.65 * (release / 250.0), 0.65, 1.35))
    else:
        discharge = float(parameters.get("initial_discharge_m3s") or 250.0)
        width = float(parameters.get("breach_width_m") or 50.0)
        depth_m = float(parameters.get("breach_depth_m") or 10.0)
        severity = 0.55 * (discharge / 250.0) + 0.25 * (width / 50.0) + 0.20 * (depth_m / 10.0)
        severity = float(np.clip(0.65 + 0.55 * severity, 0.55, 1.40))
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    return severity, seed


def _load_input_grid(dem_raster: str | Path | None) -> tuple[np.ndarray, dict[str, Any]]:
    if dem_raster and Path(dem_raster).is_file():
        with rasterio.open(dem_raster) as src:
            max_dim = 480
            scale = min(1.0, max_dim / max(src.height, src.width))
            out_h = max(24, int(round(src.height * scale)))
            out_w = max(24, int(round(src.width * scale)))
            dem = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.bilinear).astype("float32")
            transform = src.transform * src.transform.scale(src.width / out_w, src.height / out_h)
            profile = src.profile.copy()
            profile.update(
                height=out_h,
                width=out_w,
                transform=transform,
                count=1,
                dtype="float32",
                nodata=src.nodata if src.nodata is not None else -9999.0,
            )
            invalid = ~np.isfinite(dem)
            if src.nodata is not None:
                invalid |= np.isclose(dem, src.nodata)
            valid = dem[~invalid]
            if valid.size:
                fill = float(np.nanmedian(valid))
                dem[invalid] = fill
            return dem, profile

    y, x = np.mgrid[0:DEMO_HEIGHT, 0:DEMO_WIDTH]
    dem = 112.0 + 0.028 * x + 0.022 * y + 4.5 * np.sin(x / 26.0) * np.cos(y / 33.0)
    profile = {
        "driver": "GTiff",
        "height": DEMO_HEIGHT,
        "width": DEMO_WIDTH,
        "count": 1,
        "dtype": "float32",
        "crs": DEMO_CRS,
        "transform": from_origin(DEMO_ORIGIN_X, DEMO_ORIGIN_Y, DEMO_RESOLUTION_M, DEMO_RESOLUTION_M),
        "compress": "deflate",
        "nodata": -9999.0,
    }
    return dem.astype("float32"), profile


def _river_mask(river_vector: str | Path | None, profile: dict[str, Any], dem_shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(dem_shape, dtype="uint8")
    if river_vector and Path(river_vector).is_file():
        try:
            gdf = gpd.read_file(river_vector)
            if not gdf.empty:
                target_crs = profile.get("crs")
                if gdf.crs is None:
                    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
                if target_crs:
                    gdf = gdf.to_crs(target_crs)
                geometries = [geom for geom in gdf.geometry if geom is not None and not geom.is_empty]
                if geometries:
                    mask = rasterize(
                        [(geom, 1) for geom in geometries],
                        out_shape=dem_shape,
                        transform=profile["transform"],
                        fill=0,
                        all_touched=True,
                        dtype="uint8",
                    )
        except Exception:
            mask.fill(0)
    if mask.any():
        return mask.astype(bool)

    # Fallback only when no usable river geometry is available: use the lowest
    # terrain corridor as the hydraulic centreline.
    yy = np.linspace(-1.0, 1.0, dem_shape[0])[:, None]
    xx = np.linspace(-1.0, 1.0, dem_shape[1])[None, :]
    corridor = np.abs(yy - 0.28 * np.sin(xx * math.pi) - 0.12 * xx) < 0.025
    return corridor


def generate_demo_case(
    workdir: Path,
    *,
    variant_parameters: dict[str, Any] | None = None,
    dem_raster: str | Path | None = None,
    river_vector: str | Path | None = None,
    run_signature: str | None = None,
    model: str = "sph",
) -> dict[str, Any]:
    """Create deterministic, plausible browser-visible flood artifacts.

    When a prepared DEM/river is supplied, the generated result follows that study
    grid and river geometry. The fallback remains solver-free but uses the same
    normal result/analysis/export contracts as a native run.
    """
    model = str(model).lower()
    if model not in {"sph", "delft3d"}:
        raise ValueError("Demo model must be sph or delft3d.")
    workdir = Path(workdir).resolve()
    output = workdir / "analysis_engine"
    output.mkdir(parents=True, exist_ok=True)

    dem, profile = _load_input_grid(dem_raster)
    river_mask = _river_mask(river_vector, profile, dem.shape)
    pixel_x = abs(float(profile["transform"].a)) or DEMO_RESOLUTION_M
    pixel_y = abs(float(profile["transform"].e)) or DEMO_RESOLUTION_M
    pixel_size = float((pixel_x + pixel_y) / 2.0)

    severity, seed = _variant_signature(variant_parameters)
    if run_signature:
        seed ^= int(hashlib.sha256(run_signature.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    distance_px = distance_transform_edt(~river_mask)
    distance_m = distance_px * pixel_size
    valid_dem = np.isfinite(dem)
    low = dem[valid_dem]
    dem_range = float(np.nanpercentile(low, 95) - np.nanpercentile(low, 5)) if low.size else 1.0
    dem_range = max(dem_range, 0.1)
    terrain_low = np.clip((np.nanpercentile(low, 95) - dem) / dem_range, 0.0, 1.0)

    # Scenario-dependent footprint: stronger releases deepen the water and extend
    # the lateral reach. Each model uses a slightly different numerical response
    # so cross-model comparisons remain meaningful even without an installed solver.
    if model == "delft3d":
        base_depth = 1.85 + 2.45 * severity
        decay_m = 620.0 + 500.0 * severity
        reach_m = 1500.0 + 1650.0 * severity
    else:
        base_depth = 2.0 + 2.7 * severity
        decay_m = 550.0 + 520.0 * severity
        reach_m = 1600.0 + 1800.0 * severity
    texture = gaussian_filter(rng.normal(0.0, 1.0, dem.shape), sigma=10.0)
    texture = texture / max(float(np.std(texture)), 1e-6)
    longitudinal = np.linspace(1.12, 0.82, dem.shape[0], dtype="float32")[:, None]

    depth = base_depth * np.exp(-distance_m / decay_m)
    depth *= (0.72 + 0.62 * terrain_low)
    depth *= longitudinal
    depth *= (1.0 + 0.045 * texture)
    depth[distance_m > reach_m] = 0.0
    depth = np.clip(depth, 0.0, 8.0)
    depth[~valid_dem] = 0.0

    threshold = 0.05
    velocity_factor = 0.86 if model == "delft3d" else 0.92
    velocity = np.where(depth > threshold, 0.45 + velocity_factor * np.sqrt(depth) + 0.10 * severity, 0.0)
    velocity = np.clip(velocity, 0.0, 5.5)
    travel_seconds = distance_m / np.maximum(velocity, 0.45)
    arrival_offset = 8.0 * 60.0 if model == "delft3d" else 7.0 * 60.0
    arrival = np.where(depth > threshold, arrival_offset + travel_seconds, 0.0)
    arrival = np.clip(arrival, 0.0, max(180.0 * 60.0, float(variant_parameters.get("simulation_duration_s", 3600.0) if variant_parameters else 3600.0)))
    water_level = dem + depth

    dem_path = output / "study_dem.tif"
    depth_path = output / "water_depth_raster.tif"
    velocity_path = output / "velocity_raster.tif"
    arrival_path = output / "arrival_time_raster.tif"
    level_path = output / "water_level_raster.tif"
    discharge_path = output / "discharge.csv"

    _write_raster(dem_path, dem, profile=profile)
    _write_raster(depth_path, depth, profile=profile)
    _write_raster(velocity_path, velocity, profile=profile)
    _write_raster(arrival_path, arrival, profile=profile)
    _write_raster(level_path, water_level, profile=profile)

    release_mode = str((variant_parameters or {}).get("release_mode") or "dam_breach")
    if release_mode == "controlled_release":
        peak_discharge = 300.0 + 190.0 * severity
    else:
        peak_discharge = 520.0 + 340.0 * severity
    if model == "delft3d":
        peak_discharge *= 0.94
    decay = 125.0 + 42.0 * severity if model == "delft3d" else 110.0 + 45.0 * severity
    with discharge_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "discharge_m3s"])
        for seconds in range(0, 301, 15):
            q = peak_discharge * math.exp(-seconds / decay) + 0.08 * peak_discharge
            writer.writerow([seconds, round(q, 3)])

    timeseries = _write_timeseries(output / "timeseries", depth, profile)
    timeline_fractions = (0.06, 0.22, 0.40, 0.60, 0.80, 1.0)
    timeline_duration_s = float(variant_parameters.get("simulation_duration_s", 3600.0) or 3600.0) if variant_parameters else 3600.0
    timeline = [
        {"index": index, "time_s": round(timeline_duration_s * fraction, 3), "path": path}
        for index, (fraction, path) in enumerate(zip(timeline_fractions, timeseries))
    ]

    manifest = {
        "model": model,
        "runtime": "automatic",
        "variant_parameters": variant_parameters or {},
        "input_dem": str(Path(dem_raster).resolve()) if dem_raster else None,
        "input_river": str(Path(river_vector).resolve()) if river_vector else None,
        "preprocessing_artifacts": {"dem": str(dem_path.resolve())},
        "artifacts": {
            "water_depth_raster": str(depth_path.resolve()),
            "velocity_raster": str(velocity_path.resolve()),
            "arrival_time_raster": str(arrival_path.resolve()),
            "water_level_raster": str(level_path.resolve()),
            "discharge_csv": str(discharge_path.resolve()),
            "time_series_water_depth": timeseries,
            "time_series_metadata": timeline,
        },
        "grid": {
            "crs": str(profile.get("crs") or DEMO_CRS),
            "width": int(dem.shape[1]),
            "height": int(dem.shape[0]),
            "resolution_m": pixel_size,
        },
    }
    manifest_path = output / "hydroshield_model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    positive_arrival = arrival[arrival > 0]
    return {
        "working_directory": str(workdir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "dem_raster": str(dem_path.resolve()),
        "water_depth_raster": str(depth_path.resolve()),
        "velocity_raster": str(velocity_path.resolve()),
        "arrival_time_raster": str(arrival_path.resolve()),
        "water_level_raster": str(level_path.resolve()),
        "discharge_csv": str(discharge_path.resolve()),
        "time_series_water_depth": timeseries,
        "time_series_metadata": timeline,
        "summary": {
            "max_water_depth_m": float(np.nanmax(depth)),
            "max_velocity_mps": float(np.nanmax(velocity)),
            "first_arrival_time_s": float(np.nanmin(positive_arrival)) if positive_arrival.size else 0.0,
            "max_water_level_m": float(np.nanmax(water_level)),
            "max_discharge_m3s": float(peak_discharge),
            "variant_scale": float(severity),
        },
    }
