from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject
from shapely.geometry import shape
from shapely.ops import unary_union


@dataclass(frozen=True)
class RasterData:
    path: Path
    array: np.ndarray
    crs: object
    transform: Affine
    nodata: float | None

    @property
    def height(self) -> int:
        return int(self.array.shape[-2])

    @property
    def width(self) -> int:
        return int(self.array.shape[-1])

    @property
    def pixel_area_m2(self) -> float:
        return abs(float(self.transform.a * self.transform.e))


def read_single_band(path: str | Path, *, name: str) -> RasterData:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"{name} raster does not exist: {path}")
    try:
        with rasterio.open(path) as src:
            if src.count != 1:
                raise ValueError(f"{name} raster must contain exactly one band.")
            if src.crs is None:
                raise ValueError(f"{name} raster has no CRS.")
            array = src.read(1, masked=True).filled(np.nan).astype("float64")
            return RasterData(path, array, src.crs, src.transform, src.nodata)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Unable to read {name} raster: {exc}") from exc


def _same_grid(a: RasterData, b: RasterData, *, atol: float = 1e-9) -> bool:
    return (
        a.crs == b.crs
        and a.array.shape == b.array.shape
        and np.allclose(tuple(a.transform), tuple(b.transform), rtol=0, atol=atol)
    )


def align_to_reference(source: RasterData, reference: RasterData, *, kind: Literal["continuous", "mask"] = "continuous") -> np.ndarray:
    if _same_grid(source, reference):
        return source.array.copy()

    destination = np.full(reference.array.shape, np.nan, dtype="float64")
    reproject(
        source=source.array.astype("float64"),
        destination=destination,
        src_transform=source.transform,
        src_crs=source.crs,
        dst_transform=reference.transform,
        dst_crs=reference.crs,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.nearest if kind == "mask" else Resampling.bilinear,
    )
    return destination


def validate_projected(raster: RasterData) -> None:
    if not bool(getattr(raster.crs, "is_projected", False)):
        raise ValueError(
            f"Analysis raster '{raster.path.name}' must use a projected CRS with linear units; "
            "run it through Phase 4 preprocessing first."
        )


def flood_mask(depth: RasterData, threshold_m: float) -> np.ndarray:
    if threshold_m < 0:
        raise ValueError("Flood depth threshold must be non-negative.")
    validate_projected(depth)
    finite = np.isfinite(depth.array)
    return finite & (depth.array > threshold_m)


def inundated_area_m2(mask: np.ndarray, transform: Affine) -> float:
    pixel_area = abs(float(transform.a * transform.e))
    return float(np.count_nonzero(mask) * pixel_area)


def polygon_from_mask(mask: np.ndarray, transform: Affine):
    geometries = [shape(geom) for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=transform) if value == 1]
    if not geometries:
        return None
    return unary_union(geometries)


def write_mask_raster(path: Path, mask: np.ndarray, reference: RasterData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=reference.width,
        height=reference.height,
        count=1,
        dtype="uint8",
        crs=reference.crs,
        transform=reference.transform,
        nodata=0,
        compress="deflate",
    ) as dst:
        dst.write(mask.astype("uint8"), 1)


def write_float_raster(path: Path, array: np.ndarray, reference: RasterData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    valid = np.isfinite(array)
    output = np.where(valid, array, -9999.0).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=reference.width,
        height=reference.height,
        count=1,
        dtype="float32",
        crs=reference.crs,
        transform=reference.transform,
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(output, 1)


def continuous_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, float | int | None]:
    valid = np.isfinite(left) & np.isfinite(right)
    if not np.any(valid):
        return {"count": 0, "mae": None, "rmse": None, "bias": None, "max_abs_difference": None}
    diff = right[valid] - left[valid]
    return {
        "count": int(diff.size),
        "mae": float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "bias": float(np.mean(diff)),
        "max_abs_difference": float(np.max(np.abs(diff))),
    }


def flood_comparison_metrics(left_mask: np.ndarray, right_mask: np.ndarray, transform: Affine) -> dict[str, float | int]:
    intersection = left_mask & right_mask
    union = left_mask | right_mask
    left_only = left_mask & ~right_mask
    right_only = right_mask & ~left_mask
    area = lambda m: inundated_area_m2(m, transform)
    intersection_area = area(intersection)
    union_area = area(union)
    return {
        "left_area_m2": area(left_mask),
        "right_area_m2": area(right_mask),
        "intersection_area_m2": intersection_area,
        "union_area_m2": union_area,
        "left_only_area_m2": area(left_only),
        "right_only_area_m2": area(right_only),
        "iou": float(intersection_area / union_area) if union_area > 0 else 1.0,
    }
