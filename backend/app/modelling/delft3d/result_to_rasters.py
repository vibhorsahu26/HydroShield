from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import xarray as xr
from pyproj import CRS, Transformer
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject


DEPTH_NAMES = (
    "mesh2d_waterdepth", "mesh2d_water_depth", "waterdepth", "water_depth",
    "depth", "hs", "s1-depth", "mesh2d_s1depth",
)
LEVEL_NAMES = ("mesh2d_s1", "mesh2d_waterlevel", "waterlevel", "water_level", "s1")
UX_NAMES = ("mesh2d_ucx", "mesh2d_u_x", "ucx", "xvel", "velocity_x", "u")
UY_NAMES = ("mesh2d_ucy", "mesh2d_u_y", "ucy", "yvel", "velocity_y", "v")
X_NAMES = (
    "mesh2d_face_x", "mesh2d_face_center_x", "mesh2d_flowelem_x", "flowelem_x",
    "face_x", "x", "NetElem_x",
)
Y_NAMES = (
    "mesh2d_face_y", "mesh2d_face_center_y", "mesh2d_flowelem_y", "flowelem_y",
    "face_y", "y", "NetElem_y",
)
TIME_NAMES = ("time", "datetime", "timestep")


def _pick(ds: xr.Dataset, names: tuple[str, ...]) -> xr.DataArray | None:
    for name in names:
        if name in ds.data_vars:
            return ds[name]
        if name in ds.coords:
            return ds.coords[name]
    lowered = {str(k).lower(): k for k in ds.variables}
    for name in names:
        key = lowered.get(name.lower())
        if key is not None:
            return ds[key]
    return None


def _time_dimension(da: xr.DataArray) -> str | None:
    for name in TIME_NAMES:
        if name in da.dims:
            return name
    for dim in da.dims:
        if "time" in dim.lower():
            return dim
    return None


def _spatial_dimension(da: xr.DataArray, time_dim: str | None) -> str:
    dims = [d for d in da.dims if d != time_dim]
    known = {"nmesh2d_face", "mesh2d_face", "face", "flowelem", "nface", "nmesh2d_node", "node", "x", "y"}
    for dim in dims:
        if dim in known:
            return dim
    if len(dims) == 1:
        return dims[0]
    raise ValueError(f"Unable to determine Delft3D spatial dimension from {da.dims}.")


def _as_time_spatial(da: xr.DataArray) -> tuple[np.ndarray, list[float], str]:
    time_dim = _time_dimension(da)
    if time_dim is None:
        da = da.expand_dims(__hydroshield_time=[0.0])
        time_dim = "__hydroshield_time"
    spatial_dim = _spatial_dimension(da, time_dim)
    for dim in list(da.dims):
        if dim not in {time_dim, spatial_dim}:
            da = da.isel({dim: -1})
    da = da.transpose(time_dim, spatial_dim)
    data = np.asarray(da.values, dtype="float64")
    if data.ndim != 2:
        raise ValueError(f"Expected Delft3D time/spatial array, got {data.shape}.")
    if time_dim == "__hydroshield_time":
        times = [0.0]
    else:
        raw = ds_time_values(da, time_dim)
        times = _coerce_times(raw)
    return data, times, spatial_dim


def ds_time_values(da: xr.DataArray, time_dim: str) -> np.ndarray:
    try:
        return np.asarray(da.coords[time_dim].values)
    except Exception:
        return np.arange(da.sizes[time_dim], dtype="float64")


def _coerce_times(values: np.ndarray) -> list[float]:
    if np.issubdtype(values.dtype, np.number):
        return [float(v) for v in values.reshape(-1)]
    try:
        converted = values.astype("datetime64[s]").astype("int64")
        return [float(v) for v in converted.reshape(-1)]
    except Exception:
        return [float(i) for i in range(values.size)]


def _coord_values(da: xr.DataArray, spatial_dim: str) -> np.ndarray:
    data = da
    for dim in list(data.dims):
        if dim != spatial_dim:
            data = data.isel({dim: 0})
    if spatial_dim not in data.dims:
        if data.ndim == 1:
            return np.asarray(data.values, dtype="float64")
        raise ValueError(f"Coordinate variable {da.name!r} is not one-dimensional along {spatial_dim}.")
    data = data.transpose(spatial_dim)
    return np.asarray(data.values, dtype="float64").reshape(-1)


def _infer_source_crs(ds: xr.Dataset, xs: np.ndarray, ys: np.ndarray, dem_crs) -> CRS:
    candidates: list[Any] = []
    for key in ("crs", "spatial_ref", "epsg", "EPSG", "crs_wkt"):
        if key in ds.attrs:
            candidates.append(ds.attrs[key])
    for var in ds.variables.values():
        for key in ("spatial_ref", "crs_wkt", "epsg_code"):
            if key in var.attrs:
                candidates.append(var.attrs[key])
    for candidate in candidates:
        try:
            if isinstance(candidate, (int, float)):
                return CRS.from_epsg(int(candidate))
            text = str(candidate)
            if text.isdigit():
                return CRS.from_epsg(int(text))
            return CRS.from_user_input(text)
        except Exception:
            continue
    # Delft3D grids produced from HydroShield's automatic projected domain are
    # expected to use the same CRS as the DEM. For geographic coordinate arrays,
    # use WGS84 and reproject below.
    if np.isfinite(xs).any() and np.isfinite(ys).any():
        finite_x = xs[np.isfinite(xs)]
        finite_y = ys[np.isfinite(ys)]
        if finite_x.size and finite_y.size and np.max(np.abs(finite_x)) <= 180 and np.max(np.abs(finite_y)) <= 90:
            return CRS.from_epsg(4326)
    return CRS.from_user_input(dem_crs)


def _coords_to_cells(xs: np.ndarray, ys: np.ndarray, transform: Affine, width: int, height: int):
    if abs(transform.b) > 1e-9 or abs(transform.d) > 1e-9:
        inv = ~transform
        cols_f, rows_f = np.asarray(inv * (xs, ys), dtype="float64")
    else:
        cols_f = (xs - transform.c) / transform.a
        rows_f = (ys - transform.f) / transform.e
    cols = np.floor(cols_f).astype("int64")
    rows = np.floor(rows_f).astype("int64")
    valid = np.isfinite(cols_f) & np.isfinite(rows_f) & (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    return rows, cols, valid


def _write(path: Path, array: np.ndarray, *, crs, transform: Affine, nodata: float = -9999.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1,
        dtype="float32", crs=crs, transform=transform, nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(np.where(np.isfinite(array), array, nodata).astype("float32"), 1)




def _structured_grid_info(depth_da: xr.DataArray, x_da: xr.DataArray, y_da: xr.DataArray, time_dim: str | None):
    """Return structured-grid metadata when depth is time,y,x (or equivalent)."""
    spatial_dims = [d for d in depth_da.dims if d != time_dim]
    if len(spatial_dims) != 2:
        return None
    x_name = str(x_da.name) if x_da.name is not None else ""
    y_name = str(y_da.name) if y_da.name is not None else ""
    x_vals = np.asarray(x_da.values).reshape(-1) if x_da.ndim == 1 else None
    y_vals = np.asarray(y_da.values).reshape(-1) if y_da.ndim == 1 else None
    if x_vals is None or y_vals is None:
        return None
    x_dim = x_da.dims[0] if x_da.dims else None
    y_dim = y_da.dims[0] if y_da.dims else None
    if x_dim not in spatial_dims or y_dim not in spatial_dims or x_dim == y_dim:
        return None
    if depth_da.sizes.get(x_dim) != x_vals.size or depth_da.sizes.get(y_dim) != y_vals.size:
        return None
    if x_vals.size < 2 or y_vals.size < 2:
        return None
    if not (np.all(np.isfinite(x_vals)) and np.all(np.isfinite(y_vals))):
        return None
    dx = np.diff(x_vals)
    dy = np.diff(y_vals)
    if not (np.allclose(dx, dx[0], rtol=1e-5, atol=1e-8) and np.allclose(dy, dy[0], rtol=1e-5, atol=1e-8)):
        return None
    if abs(float(dx[0])) <= 0 or abs(float(dy[0])) <= 0:
        return None
    return {
        "x_dim": x_dim, "y_dim": y_dim,
        "x": x_vals, "y": y_vals,
        "x_name": x_name, "y_name": y_name,
    }


def _regular_grid_transform(xs: np.ndarray, ys: np.ndarray) -> tuple[Affine, bool, bool]:
    """Build a north-up affine and flags indicating whether data must be flipped."""
    x_inc = float(xs[1] - xs[0])
    y_inc = float(ys[1] - ys[0])
    x_ascending = x_inc > 0
    y_descending = y_inc < 0
    x_sorted = xs if x_ascending else xs[::-1]
    y_sorted = ys if y_descending else ys[::-1]
    dx = abs(x_inc)
    dy = abs(y_inc)
    transform = from_origin(float(x_sorted[0]) - dx / 2.0, float(y_sorted[0]) + dy / 2.0, dx, dy)
    return transform, not x_ascending, not y_descending


def _structured_frame_values(da: xr.DataArray, frame_index: int, time_dim: str | None, grid: dict) -> np.ndarray:
    work = da
    if time_dim is not None and time_dim in work.dims:
        work = work.isel({time_dim: frame_index})
    work = work.transpose(grid["y_dim"], grid["x_dim"])
    return np.asarray(work.values, dtype="float64")


def _warp_structured_to_dem(
    source_array: np.ndarray,
    *,
    source_transform: Affine,
    source_crs: CRS,
    dem_crs: CRS,
    dem_transform: Affine,
    width: int,
    height: int,
) -> np.ndarray:
    destination = np.full((height, width), np.nan, dtype="float64")
    reproject(
        source=source_array,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        dst_transform=dem_transform,
        dst_crs=dem_crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return destination

def _open_dataset(path: Path) -> xr.Dataset:
    try:
        return xr.open_dataset(path)
    except Exception:
        return xr.open_dataset(path, engine="scipy")


def build_delft3d_analysis_rasters(
    *,
    working_directory: str | Path,
    dem_path: str | Path,
    output_directory: str | Path,
    flood_threshold_m: float = 0.05,
) -> dict[str, Any]:
    working_directory = Path(working_directory).resolve()
    dem_path = Path(dem_path).resolve()
    output_directory = Path(output_directory).resolve()
    nc_files = sorted(working_directory.rglob("*_map.nc")) + sorted(working_directory.rglob("*.nc"))
    if not nc_files:
        raise ValueError("No Delft3D NetCDF result file was found in the completed working directory.")
    # Prefer a map file over helper netCDF files such as flow geometry.
    nc_path = next((p for p in nc_files if p.name.lower().endswith("_map.nc")), nc_files[0])
    if not dem_path.is_file():
        raise ValueError(f"Preprocessed DEM for Delft3D analysis does not exist: {dem_path}")
    output_directory.mkdir(parents=True, exist_ok=True)

    with rasterio.open(dem_path) as dem_src:
        dem_crs = dem_src.crs
        if dem_crs is None or not bool(getattr(dem_crs, "is_projected", False)):
            raise ValueError("Preprocessed DEM for Delft3D analysis must use a projected CRS.")
        width, height = dem_src.width, dem_src.height
        transform = dem_src.transform

        with _open_dataset(nc_path) as ds:
            depth_da = _pick(ds, DEPTH_NAMES)
            if depth_da is None:
                raise ValueError(
                    f"Delft3D result {nc_path.name} has no recognized water-depth variable. Variables: {', '.join(list(ds.variables)[:40])}"
                )
            depth, times, spatial_dim = _as_time_spatial(depth_da)

            x_da = _pick(ds, X_NAMES)
            y_da = _pick(ds, Y_NAMES)
            if x_da is None or y_da is None:
                # Support rectilinear arrays using explicit x/y coordinates.
                for name in ("x", "mesh2d_nodex", "mesh2d_face_x"):
                    if x_da is None and name in ds.variables:
                        x_da = ds[name]
                for name in ("y", "mesh2d_nodey", "mesh2d_face_y"):
                    if y_da is None and name in ds.variables:
                        y_da = ds[name]
            if x_da is None or y_da is None:
                raise ValueError(f"Delft3D result {nc_path.name} has no recognizable face/node X/Y coordinates for rasterisation.")

            # Structured Delft3D outputs can be stored as time,y,x arrays with
            # separate 1-D x/y coordinates. Handle those before the unstructured
            # face/node path below.
            structured_grid = _structured_grid_info(depth_da, x_da, y_da, _time_dimension(depth_da))
            if structured_grid is not None and str(x_da.name).lower() in {"x", "mesh2d_nodex", "mesh2d_face_x", "flowelem_x"} and str(y_da.name).lower() in {"y", "mesh2d_nodey", "mesh2d_face_y", "flowelem_y"}:
                time_dim = _time_dimension(depth_da)
                if time_dim is None:
                    depth_values = depth_da.expand_dims(__hydroshield_time=[0]).transpose("__hydroshield_time", structured_grid["y_dim"], structured_grid["x_dim"])
                    times = [0.0]
                else:
                    depth_values = depth_da.transpose(time_dim, structured_grid["y_dim"], structured_grid["x_dim"])
                    times = _coerce_times(ds_time_values(depth_values, time_dim))
                source_crs = _infer_source_crs(ds, structured_grid["x"], structured_grid["y"], dem_crs)
                source_transform, flip_x, flip_y = _regular_grid_transform(structured_grid["x"], structured_grid["y"])

                def prep_structured(da):
                    if da is None:
                        return None
                    data = da
                    tdim = _time_dimension(data)
                    if tdim is None:
                        data = data.expand_dims(__hydroshield_time=[0])
                        tdim = "__hydroshield_time"
                    if structured_grid["x_dim"] not in data.dims or structured_grid["y_dim"] not in data.dims:
                        return None
                    data = data.transpose(tdim, structured_grid["y_dim"], structured_grid["x_dim"])
                    return data

                ux_struct = prep_structured(_pick(ds, UX_NAMES))
                uy_struct = prep_structured(_pick(ds, UY_NAMES))
                level_struct = prep_structured(_pick(ds, LEVEL_NAMES))
                max_depth = np.full((height, width), np.nan, dtype="float64")
                max_speed = np.full((height, width), np.nan, dtype="float64")
                max_level = np.full((height, width), np.nan, dtype="float64")
                arrival = np.full((height, width), np.nan, dtype="float64")
                used_frames = 0
                for ti in range(depth_values.sizes[depth_values.dims[0]]):
                    frame_depth = _structured_frame_values(depth_values, ti, depth_values.dims[0], structured_grid)
                    if flip_x:
                        frame_depth = frame_depth[:, ::-1]
                    if flip_y:
                        frame_depth = frame_depth[::-1, :]
                    warped_depth = _warp_structured_to_dem(frame_depth, source_transform=source_transform, source_crs=source_crs, dem_crs=dem_crs, dem_transform=transform, width=width, height=height)
                    warped_depth = np.where(np.isfinite(warped_depth), np.maximum(warped_depth, 0.0), np.nan)
                    max_depth = np.where(np.isfinite(warped_depth), np.where(np.isfinite(max_depth), np.maximum(max_depth, warped_depth), warped_depth), max_depth)
                    if ux_struct is not None and uy_struct is not None:
                        uxv = _structured_frame_values(ux_struct, ti, ux_struct.dims[0], structured_grid)
                        uyv = _structured_frame_values(uy_struct, ti, uy_struct.dims[0], structured_grid)
                        if flip_x:
                            uxv = uxv[:, ::-1]; uyv = uyv[:, ::-1]
                        if flip_y:
                            uxv = uxv[::-1, :]; uyv = uyv[::-1, :]
                        speed = _warp_structured_to_dem(np.hypot(uxv, uyv), source_transform=source_transform, source_crs=source_crs, dem_crs=dem_crs, dem_transform=transform, width=width, height=height)
                        max_speed = np.where(np.isfinite(speed), np.where(np.isfinite(max_speed), np.maximum(max_speed, speed), speed), max_speed)
                    if level_struct is not None:
                        lv = _structured_frame_values(level_struct, ti, level_struct.dims[0], structured_grid)
                        if flip_x:
                            lv = lv[:, ::-1]
                        if flip_y:
                            lv = lv[::-1, :]
                        level_grid = _warp_structured_to_dem(lv, source_transform=source_transform, source_crs=source_crs, dem_crs=dem_crs, dem_transform=transform, width=width, height=height)
                        max_level = np.where(np.isfinite(level_grid), np.where(np.isfinite(max_level), np.maximum(max_level, level_grid), level_grid), max_level)
                    arrived = ~np.isfinite(arrival) & np.isfinite(warped_depth) & (warped_depth > flood_threshold_m)
                    arrival[arrived] = float(times[ti])
                    used_frames += 1

                max_speed[(~np.isfinite(max_depth)) | (max_depth <= 0)] = np.nan
                arrival[(~np.isfinite(max_depth)) | (max_depth <= flood_threshold_m)] = np.nan
                if not np.isfinite(max_level).any():
                    dem_values = dem_src.read(1, masked=True).filled(np.nan).astype("float64")
                    max_level = np.where(np.isfinite(max_depth), dem_values + max_depth, np.nan)
                depth_path = output_directory / "water_depth_max.tif"
                velocity_path = output_directory / "velocity_max.tif"
                arrival_path = output_directory / "arrival_time.tif"
                level_path = output_directory / "water_level_max.tif"
                _write(depth_path, max_depth, crs=dem_crs, transform=transform)
                _write(velocity_path, max_speed, crs=dem_crs, transform=transform)
                _write(arrival_path, arrival, crs=dem_crs, transform=transform)
                _write(level_path, max_level, crs=dem_crs, transform=transform)
                finite_depth = max_depth[np.isfinite(max_depth)]
                finite_speed = max_speed[np.isfinite(max_speed)]
                arrival_values = arrival[np.isfinite(arrival)]
                return {
                    "water_depth_raster": str(depth_path.resolve()),
                    "velocity_raster": str(velocity_path.resolve()),
                    "arrival_time_raster": str(arrival_path.resolve()),
                    "water_level_raster": str(level_path.resolve()),
                    "summary": {
                        "time_steps": int(depth_values.sizes[depth_values.dims[0]]),
                        "frames_with_spatial_output": int(used_frames),
                        "max_water_depth_m": float(np.max(finite_depth)) if finite_depth.size else 0.0,
                        "max_velocity_mps": float(np.max(finite_speed)) if finite_speed.size else 0.0,
                        "first_arrival_time_s": float(np.min(arrival_values)) if arrival_values.size else None,
                        "inundated_cell_count": int(np.count_nonzero(np.isfinite(max_depth) & (max_depth > flood_threshold_m))),
                    },
                    "warnings": [
                        "Delft3D structured-grid native results are reprojected to the preprocessed DEM grid for HydroShield's common analysis contract.",
                        "Continuous fields use bilinear resampling; maximum values are accumulated across model frames.",
                    ],
                    "provenance": {
                        "netcdf_path": str(nc_path), "dem_path": str(dem_path),
                        "crs": str(dem_crs), "source_crs": str(source_crs),
                        "grid_shape": [height, width], "source_grid": [int(len(structured_grid["y"])), int(len(structured_grid["x"]))],
                        "representation": "structured",
                    },
                }

            xs = _coord_values(x_da, spatial_dim)
            ys = _coord_values(y_da, spatial_dim)
            if len(xs) != depth.shape[1] or len(ys) != depth.shape[1]:
                raise ValueError(
                    f"Delft3D coordinate length does not match water-depth cells: depth={depth.shape[1]}, x={len(xs)}, y={len(ys)}."
                )

            source_crs = _infer_source_crs(ds, xs, ys, dem_crs)
            if CRS.from_user_input(source_crs) != CRS.from_user_input(dem_crs):
                transformer = Transformer.from_crs(source_crs, dem_crs, always_xy=True)
                xs, ys = transformer.transform(xs, ys)

            rows, cols, in_bounds = _coords_to_cells(xs, ys, transform, width, height)
            finite_xy = np.isfinite(xs) & np.isfinite(ys)
            overlap_count = int(np.count_nonzero(in_bounds & finite_xy))
            if overlap_count == 0:
                with rasterio.open(dem_path) as src:
                    bounds = src.bounds
                raise ValueError(
                    "Delft3D result coordinates do not overlap the preprocessed DEM grid. "
                    f"DEM bounds=({bounds.left}, {bounds.bottom}, {bounds.right}, {bounds.top}); "
                    f"result coordinate bounds=({np.nanmin(xs)}, {np.nanmin(ys)}, {np.nanmax(xs)}, {np.nanmax(ys)}); "
                    f"source_crs={source_crs}, dem_crs={dem_crs}."
                )

            ux_da = _pick(ds, UX_NAMES)
            uy_da = _pick(ds, UY_NAMES)
            level_da = _pick(ds, LEVEL_NAMES)
            ux = uy = level = None
            if ux_da is not None and uy_da is not None:
                ux, _, ux_spatial = _as_time_spatial(ux_da)
                uy, _, uy_spatial = _as_time_spatial(uy_da)
                if ux.shape != depth.shape or uy.shape != depth.shape or ux_spatial != spatial_dim or uy_spatial != spatial_dim:
                    ux = uy = None
            if level_da is not None:
                try:
                    level, _, level_spatial = _as_time_spatial(level_da)
                    if level.shape != depth.shape or level_spatial != spatial_dim:
                        level = None
                except ValueError:
                    level = None

            max_depth = np.full((height, width), np.nan, dtype="float64")
            max_speed = np.full((height, width), np.nan, dtype="float64")
            max_level = np.full((height, width), np.nan, dtype="float64")
            arrival = np.full((height, width), np.nan, dtype="float64")
            used_frames = 0
            for ti in range(depth.shape[0]):
                frame_depth = depth[ti]
                valid = in_bounds & np.isfinite(frame_depth)
                if not np.any(valid):
                    continue
                frame = np.full((height * width,), -np.inf, dtype="float64")
                flat = rows[valid] * width + cols[valid]
                np.maximum.at(frame, flat, np.maximum(frame_depth[valid], 0.0))
                frame = frame.reshape(height, width)
                finite_frame = np.isfinite(frame)
                max_depth = np.where(finite_frame, np.where(np.isfinite(max_depth), np.maximum(max_depth, frame), frame), max_depth)

                if ux is not None and uy is not None:
                    speed_values = np.sqrt(ux[ti] * ux[ti] + uy[ti] * uy[ti])
                    fs = np.full((height * width,), -np.inf, dtype="float64")
                    valid_speed = valid & np.isfinite(speed_values)
                    if np.any(valid_speed):
                        np.maximum.at(fs, rows[valid_speed] * width + cols[valid_speed], speed_values[valid_speed])
                        fs = fs.reshape(height, width)
                        finite_speed = np.isfinite(fs)
                        max_speed = np.where(finite_speed, np.where(np.isfinite(max_speed), np.maximum(max_speed, fs), fs), max_speed)
                elif ux is None and uy is None:
                    pass

                if level is not None:
                    fl = np.full((height * width,), -np.inf, dtype="float64")
                    valid_level = valid & np.isfinite(level[ti])
                    if np.any(valid_level):
                        np.maximum.at(fl, rows[valid_level] * width + cols[valid_level], level[ti][valid_level])
                        fl = fl.reshape(height, width)
                        finite_level = np.isfinite(fl)
                        max_level = np.where(finite_level, np.where(np.isfinite(max_level), np.maximum(max_level, fl), fl), max_level)

                arrived = ~np.isfinite(arrival) & finite_frame & (frame > flood_threshold_m)
                if np.any(arrived):
                    arrival[arrived] = float(times[ti])
                used_frames += 1

            max_depth[~np.isfinite(max_depth)] = np.nan
            max_speed[~np.isfinite(max_speed)] = np.nan
            max_speed[(~np.isfinite(max_depth)) | (max_depth <= 0)] = np.nan
            arrival[(~np.isfinite(max_depth)) | (max_depth <= flood_threshold_m)] = np.nan
            max_level[~np.isfinite(max_level)] = np.nan
            if not np.isfinite(max_level).any():
                # When the model omits an explicit water-surface/elevation variable,
                # construct the common HydroShield water-level artifact from the DEM
                # plus the reconstructed maximum depth.
                with rasterio.open(dem_path) as dem_ref:
                    dem_values = dem_ref.read(1, masked=True).filled(np.nan).astype("float64")
                max_level = np.where(np.isfinite(max_depth), dem_values + max_depth, np.nan)

            depth_path = output_directory / "water_depth_max.tif"
            velocity_path = output_directory / "velocity_max.tif"
            arrival_path = output_directory / "arrival_time.tif"
            level_path = output_directory / "water_level_max.tif"
            _write(depth_path, max_depth, crs=dem_crs, transform=transform)
            _write(velocity_path, max_speed, crs=dem_crs, transform=transform)
            _write(arrival_path, arrival, crs=dem_crs, transform=transform)
            _write(level_path, max_level, crs=dem_crs, transform=transform)

    finite_depth = max_depth[np.isfinite(max_depth)]
    finite_speed = max_speed[np.isfinite(max_speed)]
    arrival_values = arrival[np.isfinite(arrival)]
    return {
        "water_depth_raster": str(depth_path.resolve()),
        "velocity_raster": str(velocity_path.resolve()),
        "arrival_time_raster": str(arrival_path.resolve()),
        "water_level_raster": str(level_path.resolve()),
        "summary": {
            "time_steps": int(depth.shape[0]),
            "frames_with_spatial_output": int(used_frames),
            "max_water_depth_m": float(np.max(finite_depth)) if finite_depth.size else 0.0,
            "max_velocity_mps": float(np.max(finite_speed)) if finite_speed.size else 0.0,
            "first_arrival_time_s": float(np.min(arrival_values)) if arrival_values.size else None,
            "inundated_cell_count": int(np.count_nonzero(np.isfinite(max_depth) & (max_depth > flood_threshold_m))),
        },
        "warnings": [
            "Delft3D native results are rasterized onto the preprocessed DEM grid for HydroShield's common analysis contract.",
            "Face/node values are aggregated by maximum value per DEM cell across each model output frame.",
        ],
        "provenance": {
            "netcdf_path": str(nc_path),
            "dem_path": str(dem_path),
            "crs": str(dem_crs),
            "source_crs": str(source_crs),
            "grid_shape": [height, width],
            "source_spatial_dimension": spatial_dim,
            "time_steps": int(depth.shape[0]),
            "source_coordinate_overlap_count": overlap_count,
        },
    }
