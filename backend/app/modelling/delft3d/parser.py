from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

WATER_DEPTH = ("mesh2d_waterdepth", "waterdepth")
WATER_LEVEL = ("mesh2d_s1", "waterlevel")
U_X = ("mesh2d_ucx", "xvel")
U_Y = ("mesh2d_ucy", "yvel")
FACE_AREA = ("mesh2d_flowelem_ba", "face_area", "flowelem_ba")
TIME = ("time",)
WET_THRESHOLD_M = 0.05


def _pick(ds: xr.Dataset, names: tuple[str, ...]):
    for name in names:
        if name in ds.data_vars:
            return ds[name]
        if name in ds.coords:
            return ds.coords[name]
    return None


def _reduce_to_time_face(da: xr.DataArray) -> xr.DataArray:
    for dim in list(da.dims):
        if dim not in {"time", "nmesh2d_face", "face", "nmesh2d_edge", "edge"}:
            da = da.isel({dim: -1})
    return da


def _as_time_face(da: xr.DataArray) -> np.ndarray:
    da = _reduce_to_time_face(da)
    if "time" not in da.dims:
        da = da.expand_dims(time=[0])
    non_time = [dim for dim in da.dims if dim != "time"]
    if len(non_time) != 1:
        raise ValueError(f"Expected a time + spatial dimension; got {da.dims}")
    return np.asarray(da.transpose("time", non_time[0]).values, dtype=float)


def parse_results(working_directory: Path):
    candidates = sorted(working_directory.glob("*_map.nc")) + sorted(working_directory.glob("*.nc"))
    warnings: list[str] = []
    if not candidates:
        return None, [], ["Delft3D adapter found no NetCDF map output (*.nc); result parsing is deferred until solver output exists."]

    result_path = candidates[0]
    artifacts = [p for p in working_directory.iterdir() if p.is_file()]
    try:
        try:
            ds_ctx = xr.open_dataset(result_path)
        except Exception:
            ds_ctx = xr.open_dataset(result_path, engine="scipy")
        with ds_ctx as ds:
            depth_da = _pick(ds, WATER_DEPTH)
            ux_da = _pick(ds, U_X)
            uy_da = _pick(ds, U_Y)
            area_da = _pick(ds, FACE_AREA)
            time_da = _pick(ds, TIME)

            if depth_da is None:
                return None, artifacts, ["Delft3D NetCDF output has no recognized water-depth variable."]

            depth = _as_time_face(depth_da)
            wet = np.isfinite(depth) & (depth > WET_THRESHOLD_M)
            max_depth = float(np.nanmax(depth))
            final_depth = float(np.nanmax(depth[-1]))
            time_steps = int(depth.shape[0])
            wet_cell_count = int(np.count_nonzero(wet))

            summary: dict[str, Any] = {
                "max_water_depth_m": max_depth,
                "final_max_water_depth_m": final_depth,
                "time_steps": time_steps,
                "wet_cell_count": wet_cell_count,
            }

            if ux_da is not None and uy_da is not None:
                ux = _as_time_face(ux_da)
                uy = _as_time_face(uy_da)
                if ux.shape != uy.shape:
                    warnings.append("Delft3D x/y velocity arrays have different shapes; velocity metric was omitted.")
                else:
                    speed = np.sqrt(ux**2 + uy**2)
                    summary["max_velocity_mps"] = float(np.nanmax(speed))

            if area_da is not None:
                areas = np.asarray(area_da.values, dtype=float).reshape(-1)
                if len(areas) == depth.shape[1]:
                    inundated_area = float(np.nansum(areas[np.any(wet, axis=0)]))
                    summary["inundated_area_m2"] = inundated_area
                else:
                    warnings.append("Delft3D face-area variable does not align with water-depth cells; inundated-area metric was omitted.")
            else:
                warnings.append("Delft3D output has no face-area variable; inundated-area metric was omitted.")

            if time_da is not None:
                times = np.asarray(time_da.values, dtype=float).reshape(-1)
                if times.size == depth.shape[0]:
                    wet_by_time = np.any(wet, axis=1)
                    first = np.flatnonzero(wet_by_time)
                    summary["first_arrival_time_s"] = float(times[first[0]]) if first.size else None
                else:
                    warnings.append("Delft3D time coordinate length does not match water-depth time dimension.")
            else:
                warnings.append("Delft3D output has no time coordinate; flood-arrival time was omitted.")

            return summary, artifacts, warnings
    except Exception as exc:
        return None, artifacts, [f"Delft3D NetCDF output could not be parsed: {exc}"]
