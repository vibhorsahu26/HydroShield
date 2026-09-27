from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, transform_geom


def read_dem_profile(data: bytes) -> tuple[dict, tuple[float, float, float, float]]:
    try:
        with MemoryFile(data) as memfile:
            with memfile.open() as src:
                if src.count != 1:
                    raise ValueError("DEM input must contain exactly one raster band.")
                if src.crs is None:
                    raise ValueError("DEM input has no CRS.")
                return src.profile.copy(), tuple(float(v) for v in src.bounds)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"DEM could not be opened: {exc}") from exc


def source_bounds_in_target(data: bytes, target_crs) -> tuple[float, float, float, float]:
    with MemoryFile(data) as memfile:
        with memfile.open() as src:
            from rasterio.warp import transform_bounds
            return tuple(float(v) for v in transform_bounds(src.crs, target_crs, *src.bounds, densify_pts=21))


def clip_reproject_resample_dem(
    data: bytes,
    *,
    target_crs,
    clip_geometry,
    resolution_m: float,
    output_path: Path,
) -> dict:
    with MemoryFile(data) as memfile:
        with memfile.open() as src:
            if src.count != 1:
                raise ValueError("DEM input must contain exactly one raster band.")
            if src.crs is None:
                raise ValueError("DEM input has no CRS.")

            geometry_in_source = transform_geom(target_crs, src.crs, clip_geometry.__geo_interface__, precision=15)
            clipped, clipped_transform = mask(src, [geometry_in_source], crop=True, filled=False)
            if clipped.size == 0 or clipped.shape[1] < 2 or clipped.shape[2] < 2:
                raise ValueError("Computational domain does not overlap enough valid DEM area to build a raster.")

            source_bounds = rasterio.transform.array_bounds(clipped.shape[1], clipped.shape[2], clipped_transform)
            dst_transform, dst_width, dst_height = calculate_default_transform(
                src.crs,
                target_crs,
                clipped.shape[2],
                clipped.shape[1],
                *source_bounds,
                resolution=(resolution_m, resolution_m),
            )
            destination = np.full((dst_height, dst_width), np.nan, dtype="float32")
            source = clipped[0].filled(np.nan).astype("float32")

            reproject(
                source=source,
                destination=destination,
                src_transform=clipped_transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=target_crs,
                src_nodata=np.nan,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )

            valid = np.isfinite(destination)
            if not valid.any():
                raise ValueError("Processed DEM contains no valid elevation cells.")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            profile = {
                "driver": "GTiff",
                "height": dst_height,
                "width": dst_width,
                "count": 1,
                "dtype": "float32",
                "crs": target_crs,
                "transform": dst_transform,
                "nodata": -9999.0,
                "compress": "deflate",
            }
            with rasterio.open(output_path, "w", **profile) as dst:
                out = np.where(valid, destination, -9999.0).astype("float32")
                dst.write(out, 1)

    with rasterio.open(output_path) as check:
        bounds = tuple(float(v) for v in check.bounds)
        valid_count = int(np.count_nonzero(check.read(1, masked=True)))
        return {
            "path": str(output_path),
            "crs": check.crs.to_string(),
            "width": int(check.width),
            "height": int(check.height),
            "count": int(check.count),
            "resolution_x": float(check.res[0]),
            "resolution_y": float(check.res[1]),
            "nodata": float(check.nodata) if check.nodata is not None else None,
            "bounds": bounds,
            "valid_cell_count": valid_count,
        }


def raster_extent_polygon(path: Path):
    from shapely.geometry import box

    with rasterio.open(path) as src:
        return box(*src.bounds), src.crs
