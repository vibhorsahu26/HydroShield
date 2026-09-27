from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely import box, make_valid
from shapely.ops import unary_union


def generate_domain(
    river_gdf: gpd.GeoDataFrame,
    dem_bounds: tuple[float, float, float, float],
    buffer_m: float,
    min_area_m2: float,
):
    """Generate a metric computational corridor around the prepared river."""
    if river_gdf.empty:
        raise ValueError("Cannot generate domain from an empty river geometry.")

    river_union = make_valid(unary_union(river_gdf.geometry))
    if river_union.is_empty:
        raise ValueError("Cannot generate domain from an empty river geometry.")

    buffered = make_valid(river_union.buffer(buffer_m))
    dem_extent = box(*dem_bounds)
    domain = make_valid(buffered.intersection(dem_extent))
    if domain.is_empty or domain.area < min_area_m2:
        raise ValueError("Generated computational domain is empty or too small after DEM intersection.")
    return domain


def write_domain_and_mask(domain, dem_path: Path, domain_path: Path, mask_path: Path) -> dict:
    with rasterio.open(dem_path) as src:
        crs = src.crs
        if crs is None:
            raise ValueError("Processed DEM has no CRS; cannot write computational domain.")

        domain_gdf = gpd.GeoDataFrame({"domain_id": [1]}, geometry=[domain], crs=crs)
        domain_path.parent.mkdir(parents=True, exist_ok=True)
        domain_gdf.to_file(domain_path, driver="GPKG", layer="domain")

        mask = geometry_mask(
            [domain.__geo_interface__],
            transform=src.transform,
            invert=True,
            out_shape=(src.height, src.width),
        )
        profile = src.profile.copy()
        profile.update(dtype="uint8", count=1, nodata=0, compress="deflate", tiled=False)
        with rasterio.open(mask_path, "w", **profile) as dst:
            dst.write(mask.astype(np.uint8), 1)

        bounds = tuple(float(v) for v in domain.bounds)

    return {
        "path": str(domain_path),
        "mask_raster_path": str(mask_path),
        "crs": crs.to_string(),
        "area_m2": float(domain.area),
        "bounds": bounds,
        "feature_count": 1,
    }
