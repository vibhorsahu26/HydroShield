from __future__ import annotations

import json
import platform
import shlex
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import rasterio

from app.modelling.base import PreparedModel
from app.modelling.manifest import write_manifest
from app.modelling.schemas import SphExecutionDevice
from app.schemas.scenario_generation import ScenarioVariantParameters
from app.schemas.scenarios import SimulationModel

ADAPTER_VERSION = "2.7-dualsphysics-5.4.3-runtime-safe"
DUALSPHYSICS_VERSION = "5.4.3"

_DEFAULT_BINARIES = {
    "Linux": {
        "gencase": "GenCase_linux64",
        "gpu": "DualSPHysics5.4_linux64",
        "cpu": "DualSPHysics5.4CPU_linux64",
        "partvtk": "PartVTK_linux64",
    },
    "Windows": {
        "gencase": "GenCase_win64.exe",
        "gpu": "DualSPHysics5.4_win64.exe",
        "cpu": "DualSPHysics5.4CPU_win64.exe",
        "partvtk": "PartVTK_win64.exe",
    },
}
_TOKEN_NAMES = {
    "{HYDROSHIELD_TIME_MAX_S}": "simulation_duration_s",
    "{HYDROSHIELD_TIME_OUT_S}": "sph_output_interval_s",
    "{HYDROSHIELD_BREACH_WIDTH_M}": "breach_width_m",
    "{HYDROSHIELD_BREACH_DEPTH_M}": "breach_depth_m",
    "{HYDROSHIELD_BREACH_FORMATION_TIME_S}": "breach_formation_time_s",
    "{HYDROSHIELD_INITIAL_DISCHARGE_M3S}": "initial_discharge_m3s",
    "{HYDROSHIELD_CONTROLLED_RELEASE_DISCHARGE_M3S}": "controlled_release_discharge_m3s",
    "{HYDROSHIELD_RESERVOIR_WATER_LEVEL_M}": "initial_reservoir_water_level_m",
    "{HYDROSHIELD_RESERVOIR_VOLUME_M3}": "reservoir_volume_m3",
    "{HYDROSHIELD_BATHYMETRY_FILE}": "bathymetry_file",
}


def _as_command(value: str | Sequence[str]) -> list[str]:
    if isinstance(value, str):
        command = shlex.split(value)
    else:
        command = list(value)
    if not command:
        raise ValueError("SPH executable command must not be empty.")
    return command


def _resolve_executable(
    explicit: str | Sequence[str] | None,
    *,
    bin_dir: Path | None,
    kind: str,
) -> list[str]:
    if explicit is not None:
        return _as_command(explicit)

    if bin_dir is not None:
        binary_name = _DEFAULT_BINARIES.get(platform.system(), _DEFAULT_BINARIES["Linux"])[kind]
        candidate = Path(bin_dir) / binary_name
        return [str(candidate)]

    binary_name = _DEFAULT_BINARIES.get(platform.system(), _DEFAULT_BINARIES["Linux"])[kind]
    return [binary_name]


def _format_token_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def _write_bathymetry_xyz(dem_path: Path, output_path: Path, *, max_points: int = 250_000) -> dict[str, Any]:
    dem_path = dem_path.resolve()
    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError("Preprocessed DEM must have a CRS before SPH bathymetry preparation.")
        if src.count != 1:
            raise ValueError("Preprocessed DEM must contain exactly one band.")
        if src.width * src.height > max_points:
            stride = int(np.ceil(np.sqrt((src.width * src.height) / max_points)))
        else:
            stride = 1
        arr = src.read(1, masked=True)
        rows, cols = np.indices(arr.shape)
        selected = arr[::stride, ::stride]
        selected_rows = rows[::stride, ::stride]
        selected_cols = cols[::stride, ::stride]
        flat_values = selected.reshape(-1)
        flat_rows = selected_rows.reshape(-1)
        flat_cols = selected_cols.reshape(-1)

        lines: list[str] = []
        count = 0
        for value, row, col in zip(flat_values, flat_rows, flat_cols, strict=True):
            if np.ma.is_masked(value) or not np.isfinite(float(value)):
                continue
            x, y = rasterio.transform.xy(src.transform, int(row), int(col), offset="center")
            lines.append(f"{x:.12g} {y:.12g} {float(value):.12g}")
            count += 1

    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "source_dem": str(dem_path),
        "xyz_file": str(output_path.resolve()),
        "point_count": count,
        "stride": stride,
        "crs": src.crs.to_string(),
    }


def _write_bathymetry_csv(dem_path: Path, output_path: Path, *, max_axis: int = 96) -> dict[str, Any]:
    dem_path = dem_path.resolve()
    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError("Preprocessed DEM must have a CRS before SPH bathymetry preparation.")
        if src.count != 1:
            raise ValueError("Preprocessed DEM must contain exactly one band.")
        arr = src.read(1, masked=True)
        stride = max(1, int(np.ceil(max(arr.shape) / max_axis)))
        sampled = np.asarray(arr[::stride, ::stride], dtype=np.float64)
        sampled = np.flipud(sampled)
        row_indices = list(reversed(range(0, arr.shape[0], stride)))
        col_indices = list(range(0, arr.shape[1], stride))
        xs = [rasterio.transform.xy(src.transform, 0, int(col), offset="center")[0] for col in col_indices]
        ys = [rasterio.transform.xy(src.transform, int(row), 0, offset="center")[1] for row in row_indices]
        finite = sampled[np.isfinite(sampled)]
        fallback_z = float(np.min(finite)) if finite.size else 0.0
        sampled = np.where(np.isfinite(sampled), sampled, fallback_z)
        with output_path.open("w", encoding="utf-8", newline="") as f:
            f.write("Y \\ X => Z;" + ";".join(f"{x:.12g}" for x in xs) + "\n")
            for y, values in zip(ys, sampled, strict=True):
                f.write(f"{y:.12g};" + ";".join(f"{float(v):.12g}" for v in values) + "\n")
        return {
            "source_dem": str(dem_path),
            "csv_file": str(output_path.resolve()),
            "grid_rows": len(ys),
            "grid_columns": len(xs),
            "stride": stride,
            "crs": src.crs.to_string(),
        }


def _prepare_case_definition(
    *,
    native_input_directory: Path,
    working_directory: Path,
    case_filename: str,
    variant: ScenarioVariantParameters,
    output_interval_s: float,
    preprocessing_artifacts: dict[str, str | None],
) -> tuple[Path, dict[str, Any], list[str]]:
    source = (native_input_directory / case_filename).resolve()
    try:
        source.relative_to(native_input_directory.resolve())
    except ValueError as exc:
        raise ValueError("sph_case_filename must refer to a file inside native_input_directory.") from exc
    if not source.is_file():
        raise ValueError(f"DualSPHysics case definition not found: {source}")

    text = source.read_text(encoding="utf-8")
    warnings: list[str] = []
    context: dict[str, Any] = variant.model_dump(mode="json")
    context["sph_output_interval_s"] = output_interval_s

    bathymetry_token_present = "{HYDROSHIELD_BATHYMETRY_FILE}" in text
    dem_path = preprocessing_artifacts.get("dem")
    if bathymetry_token_present:
        if not dem_path:
            raise ValueError(
                "DualSPHysics case template contains {HYDROSHIELD_BATHYMETRY_FILE}, but no preprocessed DEM was supplied."
            )
        requested_name = "HydroShield_Bathymetry.csv" if ".csv" in text[text.find("{HYDROSHIELD_BATHYMETRY_FILE}") - 80:text.find("{HYDROSHIELD_BATHYMETRY_FILE}") + 80].lower() else "HydroShield_Bathymetry.xyz"
        bathy_path = working_directory / requested_name
        if requested_name.lower().endswith(".csv"):
            bathy_info = _write_bathymetry_csv(Path(dem_path), bathy_path)
        else:
            bathy_info = _write_bathymetry_xyz(Path(dem_path), bathy_path)
        context["bathymetry_file"] = bathy_path.name
        context["bathymetry_info"] = bathy_info
    else:
        context["bathymetry_file"] = ""
        if dem_path and not ('<drawfilecsv' in text and 'mode="bathymetry"' in text):
            warnings.append(
                "A preprocessed DEM was supplied but the DualSPHysics case template does not reference a HydroShield terrain input; the DEM is retained as provenance only."
            )

    for token, key in _TOKEN_NAMES.items():
        if token in text and key in context:
            text = text.replace(token, _format_token_value(context[key]))

    unresolved = sorted(token for token in _TOKEN_NAMES if token in text)
    if unresolved:
        raise ValueError("DualSPHysics case template has unresolved HydroShield placeholders: " + ", ".join(unresolved))

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"DualSPHysics case definition is not valid XML after parameter substitution: {exc}") from exc

    # GenCase resolves relative terrain references from the working directory
    # containing Case_Def.xml. Stage every referenced relative terrain file into
    # the execution directory before the solver starts.
    # This also makes custom/native cases deterministic instead of failing later
    # inside GenCase with a low-level "Cannot open the file" error.
    terrain_refs = [(node, "zpoints") for node in root.findall('.//zpoints')]
    terrain_refs.extend((node, "drawfilecsv") for node in root.findall('.//drawfilecsv'))
    for node, ref_kind in terrain_refs:
        filename = (node.get('file') or '').strip()
        if not filename or filename.startswith(('/', '\\')):
            continue
        referenced = Path(filename)
        source_ref = (native_input_directory / referenced).resolve()
        try:
            source_ref.relative_to(native_input_directory.resolve())
        except ValueError as exc:
            raise ValueError(
                f"DualSPHysics terrain reference '{filename}' escapes the native input directory."
            ) from exc
        target = (working_directory / referenced).resolve()
        try:
            target.relative_to(working_directory.resolve())
        except ValueError as exc:
            raise ValueError(
                f"DualSPHysics terrain reference '{filename}' escapes the working directory."
            ) from exc
        if target.is_file():
            continue
        if source_ref.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_ref, target)
            continue
        # A generated HydroShield automatic case can always reconstruct its
        # bathymetry from the processed DEM when the staged copy is unavailable.
        if referenced.name in {'HydroShield_Bathymetry.csv', 'HydroShield_Bathymetry.xyz'} and dem_path:
            target.parent.mkdir(parents=True, exist_ok=True)
            if referenced.suffix.lower() == ".csv":
                _write_bathymetry_csv(Path(dem_path), target)
            else:
                _write_bathymetry_xyz(Path(dem_path), target)
            continue
        raise ValueError(
            f"DualSPHysics case references relative terrain file '{filename}', "
            f"but it is missing from both the working directory '{working_directory}' "
            f"and native input directory '{native_input_directory}'."
        )

    case_path = working_directory / case_filename
    case_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(text, encoding="utf-8")
    return case_path, context, warnings


def build_inputs(
    *,
    variant_parameters: dict[str, Any],
    native_input_directory: Path,
    working_directory: Path,
    preprocessing_artifacts: dict[str, str | None] | None = None,
    case_filename: str = "Case_Def.xml",
    device: SphExecutionDevice = SphExecutionDevice.GPU,
    gpu_id: int = 0,
    output_interval_s: float = 1.0,
    bin_dir: Path | None = None,
    gencase_executable: str | Sequence[str] | None = None,
    solver_gpu_executable: str | Sequence[str] | None = None,
    solver_cpu_executable: str | Sequence[str] | None = None,
    partvtk_executable: str | Sequence[str] | None = None,
) -> PreparedModel:
    native_input_directory = native_input_directory.resolve()
    if not native_input_directory.is_dir():
        raise ValueError(f"DualSPHysics native input directory does not exist: {native_input_directory}")
    working_directory.mkdir(parents=True, exist_ok=True)
    preprocessing_artifacts = preprocessing_artifacts or {}
    for name, path in preprocessing_artifacts.items():
        if path is not None and not Path(path).exists():
            raise ValueError(f"Preprocessing artifact '{name}' does not exist: {path}")

    variant = ScenarioVariantParameters.model_validate(variant_parameters)
    case_path, resolved_context, warnings = _prepare_case_definition(
        native_input_directory=native_input_directory,
        working_directory=working_directory,
        case_filename=case_filename,
        variant=variant,
        output_interval_s=output_interval_s,
        preprocessing_artifacts=preprocessing_artifacts,
    )

    simulation_dir = working_directory / "dual_sphysics"
    output_dir = simulation_dir / "HydroShieldCase_out"
    case_prefix = output_dir / "HydroShieldCase"
    simulation_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    gencase = _resolve_executable(gencase_executable, bin_dir=bin_dir, kind="gencase")
    solver = _resolve_executable(
        solver_gpu_executable if device == SphExecutionDevice.GPU else solver_cpu_executable,
        bin_dir=bin_dir,
        kind="gpu" if device == SphExecutionDevice.GPU else "cpu",
    )
    partvtk = _resolve_executable(partvtk_executable, bin_dir=bin_dir, kind="partvtk")

    automatic_case = (native_input_directory / "hydroshield_auto_case.json").is_file()
    if automatic_case:
        # GenCase itself is CPU-side and can allocate substantial temporary memory.
        # Automatic workstation cases intentionally avoid diagnostic VTK generation and
        # use a small thread count; advanced/custom cases retain the full diagnostics.
        gencase_command = [*gencase, case_path.stem, str(case_prefix), "-save:bi", "-ompthreads:2"]
    else:
        gencase_command = [*gencase, case_path.stem, str(case_prefix), "-save:all"]
    compute_device_arg = f"-gpu:{gpu_id}" if device == SphExecutionDevice.GPU else "-cpu"
    solver_command = [
        *solver,
        compute_device_arg,
        str(case_prefix),
        str(output_dir),
        f"-tmax:{variant.simulation_duration_s}",
        f"-tout:{output_interval_s}",
        "-sv:binx",
        "-svres:1",
        "-svtimers:1",
    ]
    if automatic_case:
        # Cell mode is a DualSPHysics solver runtime option.
        # The v5.4 CLI parser accepts aliases H/HALF or 2H/FULL; numeric enum values
        # such as `2` are internal C++ enum values and are rejected by the CLI parser.
        # H selects the half-kernel cell mode for lower memory use.
        solver_command.append("-cellmode:H")
    particle_dir = output_dir / "particles"
    particle_prefix = particle_dir / "PartFluid"
    partvtk_command = [
        *partvtk,
        "-dirdata",
        str(output_dir / "data"),
        "-filexml",
        "AUTO",
        "-savecsv",
        str(particle_prefix),
        "-onlytype:-all,+fluid",
        "-vars:-all,+vel",
        "-csvsep:1",
        "-threads:2",
    ]

    input_payload = {
        "schema_version": "2.0",
        "engine": "DualSPHysics",
        "engine_version": DUALSPHYSICS_VERSION,
        "case_definition": str(case_path.resolve()),
        "device": device.value,
        "gpu_id": gpu_id if device == SphExecutionDevice.GPU else None,
        "output_interval_s": output_interval_s,
        "variant_parameters": variant.model_dump(mode="json"),
        "resolved_context": resolved_context,
        "preprocessing_artifacts": preprocessing_artifacts,
        "commands": {
            "gencase": gencase_command,
            "solver": solver_command,
            "partvtk": partvtk_command,
        },
    }
    (working_directory / "sph_input.json").write_text(
        json.dumps(input_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest = write_manifest(
        working_directory / "hydroshield_model_manifest.json",
        model=SimulationModel.SPH.value,
        adapter_version=ADAPTER_VERSION,
        variant_parameters={
            **variant.model_dump(mode="json"),
            "sph_engine": "DualSPHysics",
            "sph_engine_version": DUALSPHYSICS_VERSION,
            "sph_device": device.value,
            "sph_gpu_id": gpu_id if device == SphExecutionDevice.GPU else None,
            "sph_output_interval_s": output_interval_s,
        },
        native_input_directory=native_input_directory,
        preprocessing_artifacts=preprocessing_artifacts,
    )

    return PreparedModel(
        model=SimulationModel.SPH,
        adapter_version=ADAPTER_VERSION,
        working_directory=working_directory,
        manifest_path=manifest,
        command=gencase_command,
        execution_steps=[gencase_command, solver_command, partvtk_command],
        warnings=warnings,
    )
