from __future__ import annotations

import io
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import GeometryCollection


def read_vector(data: bytes, filename: str) -> gpd.GeoDataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".geojson", ".json"}:
        raise ValueError("Phase 4 vector preprocessing currently accepts GeoJSON input only.")
    try:
        gdf = gpd.read_file(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"River GeoJSON could not be opened: {exc}") from exc
    if gdf.empty:
        raise ValueError("River dataset contains no features.")
    if gdf.crs is None:
        raise ValueError("River dataset has no CRS; a source CRS is required for preprocessing.")
    if gdf.geometry.isna().all():
        raise ValueError("River dataset contains no valid geometries.")
    return gdf


def _extract_lines(geometry):
    geom = make_valid(geometry)
    if geom.is_empty:
        return None
    if geom.geom_type in {"LineString", "MultiLineString"}:
        return geom
    if isinstance(geom, GeometryCollection):
        lines = [g for g in geom.geoms if g.geom_type in {"LineString", "MultiLineString"}]
        if not lines:
            return None
        merged = gpd.GeoSeries(lines).union_all()
        return merged if merged.geom_type in {"LineString", "MultiLineString"} else None
    return None


def prepare_river(data: bytes, filename: str, target_crs, domain_geometry=None) -> gpd.GeoDataFrame:
    gdf = read_vector(data, filename).to_crs(target_crs)
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.map(_extract_lines)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        raise ValueError("River dataset has no line geometries after geometry cleaning.")

    gdf = gdf.explode(index_parts=False, ignore_index=True)
    gdf = gdf[gdf.geometry.length > 0].copy()
    if domain_geometry is not None:
        gdf["geometry"] = gdf.geometry.intersection(domain_geometry)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        gdf = gdf[gdf.geometry.length > 0].copy()
    if gdf.empty:
        raise ValueError("No river geometry intersects the generated computational domain.")
    return gdf


def write_geopackage(gdf: gpd.GeoDataFrame, path: Path, layer: str = "river") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG", layer=layer)


def vector_metadata(gdf: gpd.GeoDataFrame, path: Path):
    minx, miny, maxx, maxy = (float(v) for v in gdf.total_bounds)
    return {
        "path": str(path),
        "crs": gdf.crs.to_string(),
        "feature_count": int(len(gdf)),
        "geometry_types": sorted({str(v) for v in gdf.geometry.geom_type.unique()}),
        "bounds": (minx, miny, maxx, maxy),
        "total_length_m": float(gdf.length.sum()),
    }
