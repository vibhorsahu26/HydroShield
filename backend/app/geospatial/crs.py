from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
from pyproj import CRS, Transformer


@dataclass(frozen=True)
class ProcessingCRS:
    crs: CRS
    auto_selected: bool


def parse_crs(value: str) -> CRS:
    try:
        return CRS.from_user_input(value)
    except Exception as exc:
        raise ValueError(f"Invalid CRS '{value}': {exc}") from exc


def ensure_projected_metric(crs: CRS) -> None:
    if not crs.is_projected:
        raise ValueError(
            f"Processing CRS must be a projected CRS with metric linear units; got {crs.to_string()}."
        )
    if not crs.axis_info:
        raise ValueError(f"Processing CRS '{crs.to_string()}' does not expose axis-unit metadata.")
    unit_name = (crs.axis_info[0].unit_name or "").lower()
    if "metre" not in unit_name and "meter" not in unit_name:
        raise ValueError(
            f"Processing CRS '{crs.to_string()}' uses '{crs.axis_info[0].unit_name}', not metres."
        )


def _centroid_lon_lat(dem_crs: CRS, dem_bounds: tuple[float, float, float, float], river: gpd.GeoDataFrame) -> tuple[float, float]:
    if not river.empty:
        river_wgs84 = river.to_crs("EPSG:4326")
        centroid = river_wgs84.union_all().centroid
        if centroid.is_empty:
            pass
        else:
            return float(centroid.x), float(centroid.y)

    transformer = Transformer.from_crs(dem_crs, "EPSG:4326", always_xy=True)
    x = (dem_bounds[0] + dem_bounds[2]) / 2
    y = (dem_bounds[1] + dem_bounds[3]) / 2
    return transformer.transform(x, y)


def auto_utm_crs(dem_crs: CRS, dem_bounds: tuple[float, float, float, float], river: gpd.GeoDataFrame) -> CRS:
    lon, lat = _centroid_lon_lat(dem_crs, dem_bounds, river)
    if not (-180 <= lon <= 180 and -80 <= lat <= 84):
        raise ValueError("Could not derive a valid longitude/latitude location for automatic UTM selection.")
    zone = int((lon + 180) // 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def choose_processing_crs(
    target_crs: str | None,
    dem_crs: CRS,
    dem_bounds: tuple[float, float, float, float],
    river: gpd.GeoDataFrame,
) -> ProcessingCRS:
    # Rasterio returns rasterio.crs.CRS objects from dataset profiles while the
    # processing helpers below rely on pyproj.CRS metadata such as axis_info.
    dem_crs = CRS.from_user_input(dem_crs)
    river_crs = CRS.from_user_input(river.crs) if river.crs else None
    if target_crs:
        crs = parse_crs(target_crs)
        ensure_projected_metric(crs)
        return ProcessingCRS(crs=crs, auto_selected=False)

    if dem_crs.is_projected:
        try:
            ensure_projected_metric(dem_crs)
            return ProcessingCRS(crs=dem_crs, auto_selected=False)
        except ValueError:
            pass

    if river_crs and river_crs.is_projected:
        try:
            ensure_projected_metric(river_crs)
            return ProcessingCRS(crs=river_crs, auto_selected=False)
        except ValueError:
            pass

    crs = auto_utm_crs(dem_crs, dem_bounds, river)
    ensure_projected_metric(crs)
    return ProcessingCRS(crs=crs, auto_selected=True)
