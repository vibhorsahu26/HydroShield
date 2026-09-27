from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_origin

from app.modelling.delft3d.result_to_rasters import build_delft3d_analysis_rasters


def write_dem(path: Path) -> None:
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=4, count=1, dtype="float32",
        crs="EPSG:32643", transform=from_origin(0, 40, 10, 10), nodata=-9999,
    ) as dst:
        dst.write(np.full((4, 4), 100.0, dtype="float32"), 1)


def write_map(path: Path) -> None:
    # Two time frames and four face/cell centres that fall on the DEM grid.
    ds = xr.Dataset(
        data_vars={
            "mesh2d_waterdepth": (("time", "nmesh2d_face"), np.array([
                [0.0, 0.2, 0.0, 0.0],
                [0.0, 0.8, 0.5, 0.0],
            ], dtype="float64")),
            "mesh2d_ucx": (("time", "nmesh2d_face"), np.array([
                [0.0, 3.0, 0.0, 0.0],
                [0.0, 4.0, 3.0, 0.0],
            ], dtype="float64")),
            "mesh2d_ucy": (("time", "nmesh2d_face"), np.array([
                [0.0, 4.0, 0.0, 0.0],
                [0.0, 3.0, 4.0, 0.0],
            ], dtype="float64")),
        },
        coords={
            "time": np.array([0.0, 60.0]),
            "nmesh2d_face": np.arange(4),
            "mesh2d_face_x": ("nmesh2d_face", np.array([5.0, 15.0, 25.0, 35.0])),
            "mesh2d_face_y": ("nmesh2d_face", np.array([35.0, 25.0, 15.0, 5.0])),
        },
        attrs={"epsg": 32643},
    )
    ds.to_netcdf(path, engine="scipy")


def test_delft3d_native_results_become_common_analysis_rasters(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    work.mkdir()
    write_map(work / "hydroshield_map.nc")

    result = build_delft3d_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        flood_threshold_m=0.05,
    )

    with rasterio.open(result["water_depth_raster"]) as src:
        depth = src.read(1)
        assert depth[1, 1] == 0.8
        assert depth[2, 2] == 0.5
        assert src.crs.to_string() == "EPSG:32643"
    with rasterio.open(result["velocity_raster"]) as src:
        velocity = src.read(1)
        assert velocity[1, 1] == 5.0
        assert velocity[2, 2] == 5.0
    with rasterio.open(result["arrival_time_raster"]) as src:
        arrival = src.read(1)
        assert arrival[1, 1] == 0.0
        assert arrival[2, 2] == 60.0

    assert result["summary"]["max_water_depth_m"] == 0.8
    assert result["summary"]["max_velocity_mps"] == 5.0
    assert result["summary"]["first_arrival_time_s"] == 0.0
    assert result["summary"]["inundated_cell_count"] == 2


def test_delft3d_native_results_report_coordinate_mismatch(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    work.mkdir()
    ds = xr.Dataset(
        {"mesh2d_waterdepth": (("time", "nmesh2d_face"), np.array([[1.0]], dtype="float64"))},
        coords={
            "time": [0.0], "nmesh2d_face": [0],
            "mesh2d_face_x": ("nmesh2d_face", [1000.0]),
            "mesh2d_face_y": ("nmesh2d_face", [1000.0]),
        }, attrs={"epsg": 32643},
    )
    ds.to_netcdf(work / "hydroshield_map.nc", engine="scipy")

    import pytest
    with pytest.raises(ValueError, match="do not overlap.*DEM bounds=.*result coordinate bounds"):
        build_delft3d_analysis_rasters(
            working_directory=work, dem_path=dem, output_directory=tmp_path / "analysis", flood_threshold_m=0.05,
        )


def test_delft3d_native_structured_grid_is_reprojected_to_dem(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"; work.mkdir()
    ds = xr.Dataset(
        {
            "mesh2d_waterdepth": (("time", "y", "x"), np.array([[[0.1, 0.2], [0.3, 0.4]], [[0.2, 0.5], [0.6, 0.1]]], dtype=float)),
            "mesh2d_ucx": (("time", "y", "x"), np.ones((2,2,2), dtype=float)),
            "mesh2d_ucy": (("time", "y", "x"), np.ones((2,2,2), dtype=float)*2),
        },
        coords={"time": [0.0, 60.0], "x": [5.0, 15.0], "y": [25.0, 15.0]},
        attrs={"epsg": 32643},
    )
    ds.to_netcdf(work / "structured_map.nc", engine="scipy")
    result = build_delft3d_analysis_rasters(working_directory=work, dem_path=dem, output_directory=tmp_path / "analysis", flood_threshold_m=0.05)
    with rasterio.open(result["water_depth_raster"]) as src:
        data = src.read(1)
        finite = data[np.isfinite(data)]
    assert finite.size > 0
    assert float(np.max(finite)) > 0.39
    assert result["summary"]["time_steps"] == 2
