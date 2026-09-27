from __future__ import annotations

import csv
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon

from app.analysis.comparison import compare_analysis_artifacts
from app.analysis.result_processor import process_result


def write_raster(path: Path, data: np.ndarray, *, origin=(0, 40), pixel=10, crs="EPSG:32643"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
        dtype="float32", crs=crs, transform=from_origin(origin[0], origin[1], pixel, pixel), nodata=-9999,
    ) as dst:
        dst.write(data.astype("float32"), 1)


def test_process_result_calculates_core_metrics_and_exposure(tmp_path):
    depth = np.array([[0.0, 0.2, 0.0], [0.5, 1.0, 0.1], [0.0, 0.8, 0.0]], dtype=float)
    velocity = np.array([[0, 1, 0], [2, 4, 1], [0, 3, 0]], dtype=float)
    arrival = np.array([[99, 10, 99], [5, 3, 7], [99, 4, 99]], dtype=float)
    dem = np.full((3, 3), 100.0)
    for name, arr in [("depth.tif", depth), ("velocity.tif", velocity), ("arrival.tif", arrival), ("dem.tif", dem)]:
        write_raster(tmp_path / name, arr, origin=(0, 30))

    discharge = tmp_path / "discharge.csv"
    with discharge.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time_s", "discharge_m3s"])
        writer.writeheader()
        writer.writerows([{"time_s": 0, "discharge_m3s": 10}, {"time_s": 5, "discharge_m3s": 25}])

    settlements = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(15, 25), Point(25, 5)],
        crs="EPSG:32643",
    )
    settlement_path = tmp_path / "settlements.geojson"
    settlements.to_file(settlement_path, driver="GeoJSON")

    result = process_result(
        water_depth_raster=str(tmp_path / "depth.tif"),
        velocity_raster=str(tmp_path / "velocity.tif"),
        arrival_time_raster=str(tmp_path / "arrival.tif"),
        water_level_raster=None,
        dem_raster=str(tmp_path / "dem.tif"),
        discharge_csv=str(discharge),
        flood_threshold_m=0.05,
        output_dir=tmp_path / "analysis",
        exposure_layers={"settlements": str(settlement_path)},
    )

    assert result["metrics"]["max_water_depth_m"] == 1.0
    assert result["metrics"]["max_velocity_mps"] == 4.0
    assert result["metrics"]["first_arrival_time_s"] == 3.0
    assert result["metrics"]["max_water_level_m"] == 101.0
    assert result["metrics"]["max_discharge_m3s"] == 25.0
    assert result["metrics"]["inundated_area_m2"] == 500.0
    assert result["exposure"]["layers"]["settlements"]["affected_count"] == 1
    assert Path(result["artifacts"]["flood_mask_raster"]).exists()
    assert Path(result["artifacts"]["flood_extent_geojson"]).exists()


def test_process_result_rejects_geographic_analysis_raster(tmp_path):
    path = tmp_path / "depth.tif"
    write_raster(path, np.ones((2, 2)), crs="EPSG:4326")
    try:
        process_result(
            water_depth_raster=str(path), velocity_raster=None, arrival_time_raster=None,
            water_level_raster=None, dem_raster=None, discharge_csv=None,
            flood_threshold_m=0.05, output_dir=tmp_path / "analysis", exposure_layers={},
        )
    except ValueError as exc:
        assert "projected CRS" in str(exc)
    else:
        raise AssertionError("Geographic analysis raster should be rejected")


def test_comparison_covers_full_spatial_union(tmp_path):
    left = np.ones((4, 4), dtype=float)
    right = np.ones((5, 5), dtype=float) * 2
    left_path = tmp_path / "left.tif"
    right_path = tmp_path / "right.tif"
    write_raster(left_path, left, origin=(0, 40))
    write_raster(right_path, right, origin=(0, 50))

    result = compare_analysis_artifacts(
        left_depth_path=str(left_path), right_depth_path=str(right_path),
        left_velocity_path=None, right_velocity_path=None,
        left_arrival_path=None, right_arrival_path=None,
        flood_threshold_m=0.05, output_dir=tmp_path / "comparison",
    )
    flood = result["metrics"]["flood"]
    assert flood["left_area_m2"] == 1600.0
    assert flood["right_area_m2"] == 2500.0
    assert flood["intersection_area_m2"] == 1600.0
    assert flood["union_area_m2"] == 2500.0
    assert flood["iou"] == 1600 / 2500
    assert result["metrics"]["depth"]["rmse"] == 1.0
    assert Path(result["artifacts"]["depth_difference_raster"]).exists()


def test_demo_exposure_fallback_completes_missing_categories():
    from app.analysis.exposure import complete_demo_exposure

    exposure = {"exposed_area_m2": 10_000_000.0, "layers": {"settlement": {"affected_count": 3, "category": "settlement"}}}
    completed = complete_demo_exposure(exposure, enabled=True)

    assert completed["layers"]["settlement"]["affected_count"] == 3
    assert completed["layers"]["road"]["fallback"] is True
    assert completed["layers"]["bridge"]["fallback"] is True
    assert completed["layers"]["critical_infrastructure"]["fallback"] is True
    assert "settlement" not in completed["presentation"]["fallback_categories"]
    assert set(completed["presentation"]["coverage"]) == {"settlement", "road", "bridge", "critical_infrastructure"}


def test_demo_exposure_fallback_disabled_does_not_mutate_real_analysis():
    from app.analysis.exposure import complete_demo_exposure

    exposure = {"exposed_area_m2": 10_000_000.0, "layers": {}}
    assert complete_demo_exposure(exposure, enabled=False) == exposure
