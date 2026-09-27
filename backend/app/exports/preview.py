from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

_ALLOWED = {
    "water_depth_raster": "water_depth_raster",
    "flood_mask_raster": "flood_mask_raster",
    "velocity_raster": "velocity_raster",
    "arrival_time_raster": "arrival_time_raster",
    "water_level_raster": "water_level_raster",
}

_RASTER_META = {
    "water_depth_raster": {"label": "Water Depth", "unit": "m", "description": "Maximum reconstructed water depth."},
    "velocity_raster": {"label": "Flow Velocity", "unit": "m/s", "description": "Maximum reconstructed particle speed."},
    "arrival_time_raster": {"label": "Flood Arrival Time", "unit": "min", "description": "First time reconstructed depth exceeds the flood threshold."},
    "water_level_raster": {"label": "Water Level", "unit": "m", "description": "Maximum reconstructed water-surface elevation."},
    "flood_mask_raster": {"label": "Flood Extent", "unit": "binary", "description": "Cells exceeding the configured flood threshold."},
}

_PALETTES = {
    "water_depth_raster": np.array([[225, 247, 250], [125, 211, 252], [14, 165, 233], [37, 99, 235], [30, 64, 175]], dtype=np.float32),
    "velocity_raster": np.array([[254, 249, 195], [253, 224, 71], [251, 146, 60], [220, 38, 38], [127, 29, 29]], dtype=np.float32),
    "arrival_time_raster": np.array([[220, 252, 231], [134, 239, 172], [250, 204, 21], [249, 115, 22], [220, 38, 38]], dtype=np.float32),
    "water_level_raster": np.array([[224, 242, 254], [147, 197, 253], [59, 130, 246], [30, 64, 175], [23, 37, 84]], dtype=np.float32),
}


def raster_metadata(artifact: str) -> dict[str, str]:
    return dict(_RASTER_META.get(artifact, {"label": artifact, "unit": "", "description": ""}))


def _normalize(values: np.ndarray, alpha: np.ndarray, artifact: str) -> np.ndarray:
    finite = values[np.isfinite(values) & alpha]
    if finite.size == 0:
        raise ValueError("Raster contains no finite previewable cells.")
    low, high = np.percentile(finite, [2, 98])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = float(finite.min()), float(finite.max())
    if high <= low:
        scaled = np.zeros(values.shape, dtype=np.float32)
    else:
        scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
        scaled = np.nan_to_num(scaled, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)
    palette = _PALETTES.get(artifact, _PALETTES["water_depth_raster"])
    positions = np.linspace(0.0, 1.0, len(palette), dtype=np.float32)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[..., channel] = np.interp(scaled, positions, palette[:, channel]).astype(np.uint8)
    rgba[..., 3] = np.where(alpha, 185, 0).astype(np.uint8)
    return rgba


def _bounds_from_transform(dst_transform, dst_width: int, dst_height: int) -> list[list[float]]:
    left = dst_transform.c
    top = dst_transform.f
    right = left + dst_width * dst_transform.a
    bottom = top + dst_height * dst_transform.e
    return [[float(min(bottom, top)), float(min(left, right))], [float(max(bottom, top)), float(max(left, right))]]


def build_raster_preview(
    source_path: str | Path,
    output_path: Path,
    *,
    mask: bool = False,
    artifact: str | None = None,
    max_value: float | None = None,
) -> tuple[list[list[float]], dict[str, float | int | str | None]]:
    source_path = Path(source_path)
    if not source_path.exists():
        raise ValueError(f"Raster artifact does not exist: {source_path}")
    artifact = artifact or "water_depth_raster"
    with rasterio.open(source_path) as src:
        if src.crs is None:
            raise ValueError("Raster artifact has no CRS.")
        dst_crs = "EPSG:4326"
        max_width = 1800
        dst_width = min(src.width, max_width)
        dst_height = max(1, int(round(src.height * (dst_width / src.width))))
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
            dst_width=dst_width, dst_height=dst_height,
        )
        source = src.read(1, masked=True)
        destination = np.full((dst_height, dst_width), np.nan, dtype=np.float32)
        reproject(
            source.astype(np.float32).filled(np.nan),
            destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest if mask else Resampling.bilinear,
        )
        alpha = np.isfinite(destination)
        if max_value is not None:
            if artifact == "arrival_time_raster":
                alpha &= destination <= float(max_value)
            else:
                alpha &= destination <= float(max_value)
        if mask:
            rgba = np.zeros((*destination.shape, 4), dtype=np.uint8)
            rgba[..., 0] = 30
            rgba[..., 1] = 144
            rgba[..., 2] = 255
            rgba[..., 3] = np.where(alpha & (destination > 0), 150, 0).astype(np.uint8)
        else:
            rgba = _normalize(destination, alpha, artifact)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG", optimize=True)
        finite = destination[np.isfinite(destination)]
        meta = raster_metadata(artifact)
        display_min = float(np.nanmin(finite)) if finite.size else None
        display_max = float(np.nanmax(finite)) if finite.size else None
        if artifact == "arrival_time_raster":
            display_min = display_min / 60.0 if display_min is not None else None
            display_max = display_max / 60.0 if display_max is not None else None
        meta.update({
            "min_value": display_min,
            "max_value": display_max,
            "width": dst_width,
            "height": dst_height,
        })
        return _bounds_from_transform(dst_transform, dst_width, dst_height), meta


def sample_raster(source_path: str | Path, *, latitude: float, longitude: float, artifact: str) -> dict[str, float | int | str | None]:
    source_path = Path(source_path)
    if not source_path.exists():
        raise ValueError(f"Raster artifact does not exist: {source_path}")
    with rasterio.open(source_path) as src:
        if src.crs is None:
            raise ValueError("Raster artifact has no CRS.")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Latitude/longitude are outside valid geographic ranges.")
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(longitude, latitude)
        row, col = src.index(x, y)
        if row < 0 or row >= src.height or col < 0 or col >= src.width:
            return {
                "inside": False,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "value": None,
                **raster_metadata(artifact),
            }
        value = src.read(1, window=((row, row + 1), (col, col + 1)), masked=True)[0, 0]
        if np.ma.is_masked(value) or not np.isfinite(float(value)):
            return {
                "inside": True,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "value": None,
                "row": int(row),
                "column": int(col),
                **raster_metadata(artifact),
            }
        display_value = float(value) / 60.0 if artifact == "arrival_time_raster" else float(value)
        return {
            "inside": True,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "value": display_value,
            "row": int(row),
            "column": int(col),
            **raster_metadata(artifact),
        }
