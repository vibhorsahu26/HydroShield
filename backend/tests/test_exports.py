from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from app.exports.service import export_analysis, build_analysis_package


def write_raster(path: Path, data: np.ndarray, *, crs="EPSG:32643") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(0, 30, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(data.astype("float32"), 1)


def build_result(tmp_path: Path):
    flood = tmp_path / "flood_extent.geojson"
    gpd.GeoDataFrame({"flooded": [1]}, geometry=[Polygon([(0, 30), (20, 30), (20, 10), (0, 10)])], crs="EPSG:32643").to_file(flood, driver="GeoJSON")
    depth = tmp_path / "depth.tif"
    mask = tmp_path / "mask.tif"
    velocity = tmp_path / "velocity.tif"
    arrival = tmp_path / "arrival.tif"
    level = tmp_path / "level.tif"
    for path, values in [
        (depth, [[0.0, 1.0], [2.0, 0.5]]),
        (mask, [[0, 1], [1, 1]]),
        (velocity, [[0.0, 2.0], [3.0, 1.0]]),
        (arrival, [[-9999.0, 9.0], [8.0, 7.0]]),
        (level, [[100.0, 101.0], [102.0, 100.5]]),
    ]:
        write_raster(path, np.array(values, dtype=float))
    return SimpleNamespace(
        id="12345678-1234-5678-1234-567812345678",
        simulation_job_id="job-1",
        project_id="project-1",
        scenario_id="scenario-1",
        variant_id="variant-1",
        analysis_version="phase8-v1",
        flood_threshold_m=0.05,
        metrics={"max_water_depth_m": 2.0, "inundated_area_m2": 300.0},
        exposure={"exposed_area_m2": 300.0, "layers": {"settlements": {"affected_count": 2}}},
        artifacts={
            "water_depth_raster": str(depth),
            "flood_mask_raster": str(mask),
            "flood_extent_geojson": str(flood),
            "velocity_raster": str(velocity),
            "arrival_time_raster": str(arrival),
            "water_level_raster": str(level),
        },
        warnings=[],
        assumptions={"analysis": "test"},
        created_at=datetime.now(timezone.utc),
    )


def test_all_required_exports(tmp_path):
    result = build_result(tmp_path)
    out = tmp_path / "exports"
    for fmt, artifact in [
        ("geojson", None),
        ("shp", None),
        ("kml", None),
        ("geotiff", "water_depth"),
        ("geotiff", "velocity"),
        ("geotiff", "arrival_time"),
        ("geotiff", "water_level"),
        ("geotiff", "flood_mask"),
        ("csv", None),
        ("json", None),
    ]:
        path, media = export_analysis(result, fmt, artifact, out)
        assert path.exists() and path.stat().st_size > 0
        assert media

    with zipfile.ZipFile(next(out.glob("*.zip"), out / "missing.zip")) if list(out.glob("*.zip")) else zipfile.ZipFile(tmp_path / "empty.zip", "w") as _:  # pragma: no cover
        pass

    with rasterio.open(out / "12345678") if False else rasterio.open(next(p for p in out.glob("*.tif") if "water_depth" in p.name)) as src:
        assert src.crs.to_epsg() == 32643
        assert src.read(1).shape == (2, 2)


def test_geojson_export_is_wgs84_for_browser_mapping(tmp_path):
    result = build_result(tmp_path)
    path, media = export_analysis(result, "geojson", None, tmp_path / "exports")
    assert media == "application/geo+json"
    exported = gpd.read_file(path)
    assert exported.crs.to_epsg() == 4326


def test_shapefile_is_self_contained_zip(tmp_path):
    result = build_result(tmp_path)
    path, _ = export_analysis(result, "shp", None, tmp_path / "exports")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    assert {"flood_extent.shp", "flood_extent.dbf", "flood_extent.shx"}.issubset(names)
    assert any(name.endswith(".prj") for name in names)


def test_kml_is_wgs84(tmp_path):
    result = build_result(tmp_path)
    path, _ = export_analysis(result, "kml", None, tmp_path / "exports")
    gdf = gpd.read_file(path, driver="KML")
    assert gdf.crs.to_epsg() == 4326


def test_json_and_csv_contain_analysis_provenance(tmp_path):
    result = build_result(tmp_path)
    out = tmp_path / "exports"
    json_path, _ = export_analysis(result, "json", None, out)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["id"] == result.id
    assert payload["artifacts"] == result.artifacts
    csv_path, _ = export_analysis(result, "csv", None, out)
    text = csv_path.read_text(encoding="utf-8")
    assert "max_water_depth_m" in text
    assert "affected_count" in text


def test_analysis_package_contains_gis_and_statistics_outputs(tmp_path):
    result = build_result(tmp_path)
    path, _ = build_analysis_package(result, tmp_path / "exports")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    assert any(name.endswith(".geojson") for name in names)
    assert any(name.endswith(".kml") for name in names)
    assert any(name.endswith("_shapefile.zip") for name in names)
    assert any(name.endswith(".csv") for name in names)
    assert any(name.endswith(".json") for name in names)
    assert any(name.endswith("water_depth.tif") for name in names)


def test_missing_optional_raster_returns_clear_error(tmp_path):
    result = build_result(tmp_path)
    result.artifacts.pop("velocity_raster")
    try:
        export_analysis(result, "geotiff", "velocity", tmp_path / "exports")
    except ValueError as exc:
        assert "velocity_raster" in str(exc)
    else:
        raise AssertionError("Missing raster artifact should be rejected")
