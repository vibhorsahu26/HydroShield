from __future__ import annotations

import io
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from app.geospatial.preprocessing import preprocess_geospatial
from app.schemas.geospatial import GeospatialPreprocessConfig


def make_dem_geotiff_wgs84(width=80, height=80):
    transform = from_origin(77.00, 28.12, 0.0015, 0.0015)
    values = np.arange(width * height, dtype=np.float32).reshape((height, width))
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
    }
    buf = io.BytesIO()
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(values, 1)
    return buf.getvalue()


def make_river_geojson():
    gdf = gpd.GeoDataFrame(
        {"name": ["Demo River"], "order": [3]},
        geometry=[LineString([(77.02, 28.045), (77.10, 28.045)])],
        crs="EPSG:4326",
    )
    return gdf.to_json().encode()


def test_preprocess_auto_selects_metric_crs_and_builds_all_artifacts(tmp_path):
    result = preprocess_geospatial(
        make_dem_geotiff_wgs84(),
        "demo.tif",
        make_river_geojson(),
        "river.geojson",
        GeospatialPreprocessConfig(resolution_m=500, river_buffer_m=1000),
        tmp_path,
    )

    assert result.processing_crs.startswith("EPSG:326")
    assert result.dem.crs == result.river.crs == result.domain.crs == result.processing_crs
    assert result.dem.width >= 2 and result.dem.height >= 2
    assert result.dem.valid_cell_count > 0
    assert result.river.feature_count >= 1
    assert result.river.total_length_m > 0
    assert result.domain.area_m2 > 1

    for path in [result.dem.path, result.river.path, result.domain.path, result.domain.mask_raster_path]:
        assert Path(path).exists()

    with rasterio.open(result.dem.path) as src:
        assert src.crs.to_string() == result.processing_crs
        assert abs(src.res[0] - 500) < 1
        assert abs(src.res[1] - 500) < 1
        assert src.width >= 2 and src.height >= 2

    with rasterio.open(result.domain.mask_raster_path) as mask_src, rasterio.open(result.dem.path) as dem_src:
        mask = mask_src.read(1)
        assert mask_src.transform == dem_src.transform
        assert mask_src.crs == dem_src.crs
        assert mask.shape == (dem_src.height, dem_src.width)
        assert int(mask.sum()) > 0

    river = gpd.read_file(result.river.path)
    domain = gpd.read_file(result.domain.path)
    assert river.crs.to_string() == result.processing_crs
    assert domain.crs.to_string() == result.processing_crs
    assert not river.empty
    assert not domain.empty


def test_preprocess_honours_explicit_processing_crs(tmp_path):
    result = preprocess_geospatial(
        make_dem_geotiff_wgs84(),
        "demo.tif",
        make_river_geojson(),
        "river.geojson",
        GeospatialPreprocessConfig(target_crs="EPSG:32643", resolution_m=1000, river_buffer_m=800),
        tmp_path,
    )
    assert result.processing_crs == "EPSG:32643"
    assert result.processing_crs_name


def test_preprocess_rejects_non_metric_target_crs(tmp_path):
    try:
        preprocess_geospatial(
            make_dem_geotiff_wgs84(),
            "demo.tif",
            make_river_geojson(),
            "river.geojson",
            GeospatialPreprocessConfig(target_crs="EPSG:4326"),
            tmp_path,
        )
    except ValueError as exc:
        assert "projected CRS" in str(exc)
    else:
        raise AssertionError("Expected non-metric target CRS to be rejected")


def test_geometry_collection_line_cleanup_preserves_target_crs():
    import geopandas as gpd
    from shapely.geometry import GeometryCollection, LineString, Polygon

    from app.geospatial.vector import prepare_river

    gdf = gpd.GeoDataFrame(
        {"name": ["mixed"]},
        geometry=[GeometryCollection([LineString([(77, 28), (77.1, 28)]), Polygon([(77, 28), (77.1, 28), (77.1, 28.1), (77, 28)])])],
        crs="EPSG:4326",
    )
    payload = gdf.to_json().encode()
    prepared = prepare_river(payload, "river.geojson", "EPSG:32643")
    assert prepared.crs.to_string() == "EPSG:32643"
    assert all(g.geom_type in {"LineString", "MultiLineString"} for g in prepared.geometry)
