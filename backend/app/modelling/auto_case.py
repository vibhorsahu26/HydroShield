from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import xarray as xr


def _safe_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Generated model parameter must be finite.")
    return number


# Automatic SPH limits are intentionally conservative for workstation/GPU demo runs.
# Advanced/custom cases are not modified and can use expert-defined domains.
AUTO_SPH_MAX_DOMAIN_M = 1200.0
AUTO_SPH_MIN_DP_M = 15.0
AUTO_SPH_MAX_DOMAIN_POINTS = 500_000


def _adjust_window(start: float, end: float, lower: float, upper: float) -> tuple[float, float]:
    length = min(max(end - start, 0.0), upper - lower)
    start = max(lower, start)
    end = start + length
    if end > upper:
        end = upper
        start = max(lower, end - length)
    return start, end


def _estimated_domain_points(width: float, height: float, top: float, dp: float) -> int:
    nx = int(math.ceil(width / dp)) + 1
    ny = int(math.ceil(height / dp)) + 1
    nz = int(math.ceil(top / dp)) + 1
    return nx * ny * nz


def generate_dualsphysics_case(*, variant_parameters: dict[str, Any], dem_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate a bounded, reproducible DualSPHysics starter case from the processed DEM.

    Automatic generation is a demonstration configuration rather than an expert-calibrated
    hydraulic model. To avoid workstation/GPU crashes from enormous computational domains, the
    automatic case is clipped to at most 1.2 km x 1.2 km around the generated dam and uses at least
    15 m particle spacing. Advanced/custom cases are left untouched.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dem_path) as src:
        if src.crs is None or src.count != 1:
            raise ValueError("Automatic DualSPHysics generation requires a single-band projected DEM with a CRS.")
        original_bounds = src.bounds
        original_width = max(original_bounds.right - original_bounds.left, abs(src.transform.a))
        original_height = max(original_bounds.top - original_bounds.bottom, abs(src.transform.e))
        source_dx = float(abs(src.transform.a))
        source_dy = float(abs(src.transform.e))

        # Place the synthetic dam at the historical 35% longitudinal location, then
        # construct a downstream-biased window no larger than 1.2 km x 1.2 km.
        wall_x_reference = original_bounds.left + 0.35 * original_width
        center_y = (original_bounds.bottom + original_bounds.top) / 2.0
        crop_width = min(original_width, AUTO_SPH_MAX_DOMAIN_M)
        crop_height = min(original_height, AUTO_SPH_MAX_DOMAIN_M)
        x0, x1 = _adjust_window(
            wall_x_reference - 0.25 * crop_width,
            wall_x_reference + 0.75 * crop_width,
            original_bounds.left,
            original_bounds.right,
        )
        y0, y1 = _adjust_window(
            center_y - 0.5 * crop_height,
            center_y + 0.5 * crop_height,
            original_bounds.bottom,
            original_bounds.top,
        )
        window = rasterio.windows.from_bounds(x0, y0, x1, y1, transform=src.transform)
        window = window.round_offsets().round_lengths()
        arr = src.read(1, window=window, masked=True)
        if np.ma.count(arr) == 0:
            raise ValueError("Automatic DualSPHysics generation requires valid elevation cells inside the automatic domain.")
        dem_transform = src.window_transform(window)
        bounds = rasterio.windows.bounds(window, src.transform)
        zmin = float(arr.min())
        zmax = float(arr.max())
        dx = source_dx
        dy = source_dy

    water_level = _safe_float(variant_parameters["initial_reservoir_water_level_m"])
    breach_width = variant_parameters.get("breach_width_m")
    breach_depth = variant_parameters.get("breach_depth_m")
    breach_time = variant_parameters.get("breach_formation_time_s")
    duration = _safe_float(variant_parameters["simulation_duration_s"])

    # Keep the automatic run practical on a local workstation. If the DEM is very fine,
    # coarse the SPH particle spacing rather than allowing an unbounded domain.
    dp = max(AUTO_SPH_MIN_DP_M, 0.5 * min(dx, dy))
    width = max(bounds[2] - bounds[0], dp)
    height = max(bounds[3] - bounds[1], dp)
    depth = max(zmax - zmin, dy)
    relative_water_level = max(0.5 * dp, water_level - zmin)
    domain_top = max(relative_water_level + dp, depth + dp)
    estimated_points = _estimated_domain_points(width, height, domain_top, dp)
    # Coarsen iteratively because vertical domain size depends on dp. A single
    # cube-root adjustment can leave high-relief DEMs above the actual budget.
    for _ in range(8):
        if estimated_points <= AUTO_SPH_MAX_DOMAIN_POINTS:
            break
        dp *= (estimated_points / AUTO_SPH_MAX_DOMAIN_POINTS) ** (1.0 / 3.0) * 1.02
        relative_water_level = max(0.5 * dp, water_level - zmin)
        domain_top = max(relative_water_level + dp, depth + dp)
        estimated_points = _estimated_domain_points(width, height, domain_top, dp)

    wall_x = bounds[0] + 0.25 * width
    gap = min(float(breach_width or 0.0), 0.8 * height)
    if gap <= 0:
        gap = max(2.0 * dp, 0.1 * height)
    dam_left_y = bounds[1]
    dam_mid_low = bounds[1] + 0.5 * height - 0.5 * gap
    dam_mid_high = bounds[1] + 0.5 * height + 0.5 * gap
    dam_right_y = bounds[3]
    wall_height = max(relative_water_level, depth) + dp

    def box(point_x: float, point_y: float, point_z: float, size_x: float, size_y: float, size_z: float, fill: str = "solid") -> ET.Element:
        draw = ET.Element("drawbox")
        ET.SubElement(draw, "boxfill").text = fill
        ET.SubElement(draw, "point", x=f"{point_x:.12g}", y=f"{point_y:.12g}", z=f"{point_z:.12g}")
        ET.SubElement(draw, "size", x=f"{max(size_x, dp):.12g}", y=f"{max(size_y, dp):.12g}", z=f"{max(size_z, dp):.12g}")
        return draw

    root = ET.Element("case", {"app": "HydroShield auto-generated"})
    casedef = ET.SubElement(root, "casedef")
    constants = ET.SubElement(casedef, "constantsdef")
    ET.SubElement(constants, "gravity", x="0", y="0", z="-9.81")
    ET.SubElement(constants, "rhop0", value="1000")
    ET.SubElement(constants, "rhopgradient", value="2")
    ET.SubElement(constants, "hswl", value=f"{relative_water_level:.12g}", auto="false")
    ET.SubElement(constants, "gamma", value="7")
    ET.SubElement(constants, "speedsystem", value="0", auto="true")
    ET.SubElement(constants, "coefsound", value="20")
    ET.SubElement(constants, "speedsound", value="0", auto="true")
    ET.SubElement(constants, "coefh", value="1.0")
    ET.SubElement(constants, "_hdp", value="2")
    ET.SubElement(constants, "cflnumber", value="0.2")
    ET.SubElement(casedef, "mkconfig", boundcount="240", fluidcount="9")
    geometry = ET.SubElement(casedef, "geometry")
    definition = ET.SubElement(geometry, "definition", dp=f"{dp:.12g}", units_comment="metres")
    ET.SubElement(definition, "pointmin", x=f"{bounds[0]:.12g}", y=f"{bounds[1]:.12g}", z=f"{zmin:.12g}")
    ET.SubElement(definition, "pointmax", x=f"{bounds[2]:.12g}", y=f"{bounds[3]:.12g}", z=f"{zmin + domain_top:.12g}")
    commands = ET.SubElement(geometry, "commands")
    mainlist = ET.SubElement(commands, "mainlist")

    ET.SubElement(mainlist, "resetdraw")
    ET.SubElement(mainlist, "setshapemode").text = "dp | bound"
    ET.SubElement(mainlist, "setdrawmode", mode="full")
    ET.SubElement(mainlist, "setmkbound", mk="0")
    mainlist.append(box(bounds[0], bounds[1], zmin, width, height, max(dp, 2 * dp), "bottom"))

    if gap < height:
        mainlist.append(box(wall_x, dam_left_y, zmin, dp, max(dam_mid_low - dam_left_y, dp), wall_height, "solid"))
        mainlist.append(box(wall_x, dam_mid_high, zmin, dp, max(dam_right_y - dam_mid_high, dp), wall_height, "solid"))

    ET.SubElement(mainlist, "setmkfluid", mk="0")
    fluid_draw = ET.SubElement(mainlist, "drawbox")
    ET.SubElement(fluid_draw, "boxfill").text = "solid"
    ET.SubElement(fluid_draw, "point", x=f"{bounds[0]:.12g}", y=f"{bounds[1]:.12g}", z=f"{zmin:.12g}")
    ET.SubElement(fluid_draw, "size", x=f"{max(wall_x - bounds[0] - dp, dp):.12g}", y=f"{height:.12g}", z=f"{max(relative_water_level, dp):.12g}")

    # Use the long-standing GenCase drawfilecsv bathymetry mechanism for
    # automatically generated cases. It avoids the v5.4.3 drawbathymetry/zpoints
    # path that can terminate GenCase with SIGSEGV on some Linux builds while
    # still carrying the DEM-derived terrain into the automatic case.
    ET.SubElement(
        mainlist,
        "drawfilecsv",
        file="HydroShield_Bathymetry.csv",
        mode="bathymetry",
    )

    execution = ET.SubElement(root, "execution")
    parameters = ET.SubElement(execution, "parameters")
    ET.SubElement(parameters, "parameter", key="TimeMax", value=f"{duration:.12g}", units_comment="seconds")
    ET.SubElement(parameters, "parameter", key="TimeOut", value=f"{min(1.0, duration):.12g}", units_comment="seconds")
    ET.SubElement(parameters, "parameter", key="StepAlgorithm", value="1")
    ET.SubElement(parameters, "parameter", key="Kernel", value="2")
    ET.SubElement(parameters, "parameter", key="ViscoTreatment", value="1")
    ET.SubElement(parameters, "parameter", key="Visco", value="0.1")
    ET.SubElement(parameters, "parameter", key="SimulationDomain", value="HydroShield")
    simulation_domain = ET.SubElement(parameters, "simulationdomain")
    ET.SubElement(simulation_domain, "posmin", x="default", y="default", z="default")
    ET.SubElement(simulation_domain, "posmax", x="default", y="default", z="default + 50%")

    bathy_path = output_dir / "HydroShield_Bathymetry.csv"
    bathy_max_axis = 96
    stride = max(1, int(np.ceil(max(arr.shape) / bathy_max_axis)))
    sampled = np.asarray(arr[::stride, ::stride], dtype=np.float64)
    # GenCase CSV bathymetry uses a regular X/Y matrix. Raster rows are usually
    # stored from north to south, so reverse rows to emit increasing Y values.
    sampled = np.flipud(sampled)
    row_indices = list(range(0, arr.shape[0], stride))
    col_indices = list(range(0, arr.shape[1], stride))
    row_indices = list(reversed(row_indices))
    xs = [rasterio.transform.xy(dem_transform, 0, int(col), offset="center")[0] for col in col_indices]
    ys = [rasterio.transform.xy(dem_transform, int(row), 0, offset="center")[1] for row in row_indices]
    finite = sampled[np.isfinite(sampled)]
    fallback_z = float(np.min(finite)) if finite.size else float(zmin)
    sampled = np.where(np.isfinite(sampled), sampled, fallback_z)
    with bathy_path.open("w", encoding="utf-8", newline="") as bathy_file:
        bathy_file.write("Y \\ X => Z;" + ";".join(f"{x:.12g}" for x in xs) + "\n")
        for y, values in zip(ys, sampled, strict=True):
            bathy_file.write(f"{y:.12g};" + ";".join(f"{float(v):.12g}" for v in values) + "\n")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    case_path = output_dir / "Case_Def.xml"
    tree.write(case_path, encoding="utf-8", xml_declaration=True)

    domain_clipped = (
        abs(bounds[0] - original_bounds.left) > source_dx
        or abs(bounds[1] - original_bounds.bottom) > source_dy
        or abs(bounds[2] - original_bounds.right) > source_dx
        or abs(bounds[3] - original_bounds.top) > source_dy
    )
    metadata = {
        "engine": "DualSPHysics",
        "engine_version": "5.4.3",
        "generation_mode": "automatic",
        "source_dem": str(dem_path.resolve()),
        "original_dem_bounds": [original_bounds.left, original_bounds.bottom, original_bounds.right, original_bounds.top],
        "domain_bounds": [bounds[0], bounds[1], bounds[2], bounds[3]],
        "domain_clipped": domain_clipped,
        "domain_max_size_m": AUTO_SPH_MAX_DOMAIN_M,
        "estimated_domain_points": estimated_points,
        "dem_resolution_m": [dx, dy],
        "particle_spacing_m": dp,
        "elevation_min_m": zmin,
        "elevation_max_m": zmax,
        "initial_water_level_m": water_level,
        "breach_width_m": breach_width,
        "breach_depth_m": breach_depth,
        "breach_formation_time_s": breach_time,
        "simulation_duration_s": duration,
        "bathymetry_csv": str(bathy_path.resolve()),
        "assumptions": [
            "Automatic SPH is bounded to a maximum 1.2 km x 1.2 km workstation window centered around the generated dam and biased downstream.",
            "Automatic SPH uses at least 15 m particle spacing and coarsens iteratively when required by the computational-point limit.",
            "Synthetic dam wall is placed near the upstream quarter of the automatic computational window.",
            "Breach opening is centered on the dam wall and sized from the scenario breach width.",
            "Hydraulic calibration, roughness and detailed structure geometry require expert/source data.",
        ],
        "warnings": [
            "Automatic SPH is a bounded demonstration configuration intended to avoid impractical workstation/GPU memory requirements.",
            "Use an expert-defined Advanced/custom case for high-resolution or full-catchment production modelling.",
        ],
    }
    (output_dir / "hydroshield_auto_case.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return {"native_input_directory": str(output_dir.resolve()), "case_filename": case_path.name, "metadata": metadata}

def generate_delft3d_case(*, variant_parameters: dict[str, Any], dem_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate a small deterministic D-Flow FM-compatible starter case.

    The grid is written using the established Deltares NetCDF net schema. This is
    intentionally conservative: no unsupported boundary-forcing assumptions are
    invented. A closed-domain cold-start case is produced, with the initial water
    level file derived from the selected scenario.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dem_path) as src:
        if src.crs is None or src.count != 1:
            raise ValueError("Automatic Delft3D generation requires a single-band projected DEM with a CRS.")
        bounds = src.bounds
        dx = float(abs(src.transform.a))
        dy = float(abs(src.transform.e))
        arr = src.read(1, masked=True)
        if np.ma.count(arr) == 0:
            raise ValueError("Automatic Delft3D generation requires a DEM with valid elevation cells.")
        zmin = float(arr.min())
        width = max(bounds.right - bounds.left, dx)
        height = max(bounds.top - bounds.bottom, dy)
        nx = max(2, min(40, int(round(width / max(dx * 3, 1.0)))))
        ny = max(2, min(40, int(round(height / max(dy * 3, 1.0)))))
        x = np.linspace(bounds.left, bounds.right, nx + 1)
        y = np.linspace(bounds.bottom, bounds.top, ny + 1)
        xx, yy = np.meshgrid(x, y, indexing="xy")
        node_x = xx.ravel()
        node_y = yy.ravel()
        sampled = list(src.sample(zip(node_x.tolist(), node_y.tolist()), indexes=1))
        node_z = np.array([float(v[0]) if len(v) and np.isfinite(float(v[0])) else zmin for v in sampled], dtype=np.float64)

    width = max(bounds.right - bounds.left, dx)
    height = max(bounds.top - bounds.bottom, dy)
    elem_nodes = []
    links = set()
    for j in range(ny):
        for i in range(nx):
            n0 = j * (nx + 1) + i + 1
            n1 = n0 + 1
            n3 = (j + 1) * (nx + 1) + i + 1
            n2 = n3 + 1
            elem_nodes.append([4, n0, n1, n2, n3])
            for a, b in ((n0, n1), (n1, n2), (n2, n3), (n3, n0)):
                links.add(tuple(sorted((a, b))))
    link_array = np.array(sorted(links), dtype=np.int32)
    elem_array = np.array(elem_nodes, dtype=np.int32)

    boundary = []
    for idx, (a, b) in enumerate(link_array, start=1):
        ax, ay = node_x[a - 1], node_y[a - 1]
        bx, by = node_x[b - 1], node_y[b - 1]
        if (np.isclose(ax, bounds.left) and np.isclose(bx, bounds.left)) or (np.isclose(ax, bounds.right) and np.isclose(bx, bounds.right)) or (np.isclose(ay, bounds.bottom) and np.isclose(by, bounds.bottom)) or (np.isclose(ay, bounds.top) and np.isclose(by, bounds.top)):
            boundary.append(idx)

    grid_path = output_dir / "hydroshield_net.nc"
    ds = xr.Dataset(
        data_vars={
            "NetNode_x": (("nNetNode",), node_x),
            "NetNode_y": (("nNetNode",), node_y),
            "NetNode_z": (("nNetNode",), node_z),
            "NetLink": (("nNetLink", "nNetLinkPts"), link_array),
            "NetLinkType": (("nNetLink",), np.full(len(link_array), 2, dtype=np.int32)),
            "NetElemNode": (("nNetElem", "nNetElemMaxNode"), elem_array),
            "BndLink": (("nBndLink",), np.array(boundary, dtype=np.int32)),
        },
        attrs={
            "institution": "HydroShield",
            "references": "https://deltares.nl/",
            "source": "HydroShield automatic starter grid",
            "Conventions": "CF-1.4/Deltares-0.1",
        },
    )
    ds.to_netcdf(grid_path, engine="scipy")

    water_level = _safe_float(variant_parameters["initial_reservoir_water_level_m"])
    water_file = output_dir / "hydroshield_waterlevel.xyz"
    water_file.write_text(
        "\n".join([
            f"{bounds.left:.12g} {bounds.bottom:.12g} {water_level:.12g}",
            f"{bounds.right:.12g} {bounds.bottom:.12g} {water_level:.12g}",
            f"{bounds.right:.12g} {bounds.top:.12g} {water_level:.12g}",
            f"{bounds.left:.12g} {bounds.top:.12g} {water_level:.12g}",
        ])
        + "\n",
        encoding="utf-8",
    )
    duration = _safe_float(variant_parameters["simulation_duration_s"])
    mdu = f"""[model]\nProgram = D-Flow FM\nMDUFormatVersion = 1.08\nAutoStart = 0\nPathsRelativeToParent = 0\n\n[geometry]\nNetFile = hydroshield_net.nc\nBathymetryFile =\nDryPointsFile =\nWaterLevIniFile = hydroshield_waterlevel.xyz\nLandBoundaryFile =\n\n[time]\nTunit = S\nTStart = 0\nTStop = {duration:.12g}\nDtMax = 60\nDtInit = 1\n\n[output]\nOutputDir = dflowfmoutput\nFlowGeomFile = hydroshield_flowgeom.nc\nMapFile = hydroshield_map.nc\nMapInterval = 60. 1.\n\n"""
    mdu_path = output_dir / "hydroshield.mdu"
    mdu_path.write_text(mdu, encoding="utf-8")

    dimr = """<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>
<dimrConfig xmlns=\"http://schemas.deltares.nl/dimr\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://schemas.deltares.nl/dimr https://content.oss.deltares.nl/schemas/dimr-1.2.xsd\">
  <documentation>
    <fileVersion>1.2</fileVersion>
    <createdBy>HydroShield</createdBy>
    <creationDate>2026-09-21T00:00:00Z</creationDate>
  </documentation>
  <control>
    <start name=\"DFlowFM\" />
  </control>
  <component name=\"DFlowFM\">
    <library>dflowfm</library>
    <process>0</process>
    <mpiCommunicator>DFM_COMM_DFMWORLD</mpiCommunicator>
    <workingDir>.</workingDir>
    <inputFile>hydroshield.mdu</inputFile>
  </component>
</dimrConfig>
"""
    dimr_path = output_dir / "dimr_config.xml"
    dimr_path.write_text(dimr, encoding="utf-8")

    metadata = {
        "engine": "Delft3D FM",
        "generation_mode": "automatic",
        "source_dem": str(dem_path.resolve()),
        "grid_file": str(grid_path.resolve()),
        "mdu_file": str(mdu_path.resolve()),
        "dimr_config": str(dimr_path.resolve()),
        "grid_dimensions": {"nx": nx, "ny": ny},
        "dem_resolution_m": [dx, dy],
        "initial_water_level_m": water_level,
        "simulation_duration_s": duration,
        "assumptions": [
            "Regular rectangular 2D starter mesh derived from the processed DEM extent.",
            "Cold-start water level is spatially uniform from the scenario value.",
            "No external boundary forcing is invented; the starter domain is closed.",
            "Hydraulic boundary conditions, friction and detailed structures require source data/calibration.",
        ],
        "warnings": [
            "Automatically generated Delft3D inputs are a prototype starter case and require hydraulic calibration before operational use.",
        ],
    }
    (output_dir / "hydroshield_auto_case.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"native_input_directory": str(output_dir.resolve()), "mdu_filename": mdu_path.name, "dimr_filename": dimr_path.name, "metadata": metadata}
