from __future__ import annotations

from pathlib import Path
from typing import Any
import shutil

from app.modelling.base import PreparedModel
from app.modelling.manifest import write_manifest
from app.modelling.schemas import Delft3DRunnerMode
from app.schemas.scenarios import SimulationModel

ADAPTER_VERSION = "1.0"


def _find_single(directory: Path, pattern: str, label: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise ValueError(f"Delft3D native input directory contains no {label}.")
    if len(matches) > 1:
        raise ValueError(
            f"Delft3D native input directory contains multiple {label}; provide exactly one."
        )
    return matches[0]



def _resolve_runner(executable: str | None, runner_mode: Delft3DRunnerMode, native_input_directory: Path) -> str:
    if executable:
        candidate = Path(executable)
        if candidate.parent != Path(".") or candidate.is_absolute():
            if not candidate.exists():
                raise ValueError(f"Delft3D executable does not exist: {candidate}")
            return str(candidate)
        found = shutil.which(executable)
        if found:
            return found
        # Preserve an explicit command name for callers/tests that provide the
        # executable in a later runtime environment. The job manager performs a
        # preflight before any real execution.
        return executable
    names = ["dimr", "run_dimr.sh", "run_dimr", "dimr.exe"] if runner_mode == Delft3DRunnerMode.DIMR else ["dflowfm", "dflowfm.exe"]
    for name in names:
        candidate = native_input_directory / name
        if candidate.exists():
            return str(candidate)
        found = shutil.which(name)
        if found:
            return found

    # Model preparation itself does not require the solver binary. Return the
    # canonical command name so an automatically generated case can be inspected
    # or exported even when the runtime is not installed. SimulationJobManager
    # performs the authoritative runtime preflight before execution.
    return names[0]

def build_inputs(
    *,
    variant_parameters: dict[str, Any],
    native_input_directory: Path,
    working_directory: Path,
    runner_mode: Delft3DRunnerMode,
    executable: str,
    preprocessing_artifacts: dict[str, str | None] | None = None,
) -> PreparedModel:
    native_input_directory = native_input_directory.resolve()
    if not native_input_directory.is_dir():
        raise ValueError(f"Delft3D native input directory does not exist: {native_input_directory}")

    working_directory.mkdir(parents=True, exist_ok=True)
    resolved_executable = _resolve_runner(executable, runner_mode, native_input_directory)

    if runner_mode == Delft3DRunnerMode.DFLOWFM:
        native_file = _find_single(
            native_input_directory,
            "*.mdu",
            "D-Flow FM .mdu model definition file",
        )
        command = [resolved_executable, "--autostartstop", str(native_file)]
    else:
        native_file = _find_single(
            native_input_directory,
            "dimr_config.xml",
            "DIMR configuration file",
        )
        command = [resolved_executable, str(native_file)]

    manifest = write_manifest(
        working_directory / "hydroshield_model_manifest.json",
        model=SimulationModel.DELFT3D.value,
        adapter_version=ADAPTER_VERSION,
        variant_parameters={**variant_parameters, "runner_mode": runner_mode.value},
        native_input_directory=native_input_directory,
        preprocessing_artifacts=preprocessing_artifacts,
    )
    return PreparedModel(
        model=SimulationModel.DELFT3D,
        adapter_version=ADAPTER_VERSION,
        working_directory=working_directory,
        manifest_path=manifest,
        command=command,
    )
