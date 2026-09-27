from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modelling.schemas import Delft3DRunnerMode, SphExecutionDevice


@dataclass(frozen=True)
class SolverRuntime:
    key: str
    ready: bool
    available: bool
    version: str | None
    device: str | None
    effective_device: str | None
    runner_mode: str | None
    binaries: dict[str, str | None]
    gpu: dict[str, Any]
    warnings: list[str]


class SolverRuntimeDetector:
    """Detect external model runtimes and choose safe execution fallbacks."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _resolve_command(value: str | None) -> str | None:
        if not value:
            return None
        candidate = Path(value)
        if candidate.is_absolute() or candidate.parent != Path('.'):
            return str(candidate) if candidate.exists() else None
        return shutil.which(value)

    @staticmethod
    def _detect_gpu() -> dict[str, Any]:
        result: dict[str, Any] = {"available": False, "count": 0, "devices": [], "source": None}
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                completed = subprocess.run(
                    [nvidia_smi, "--query-gpu=index,name,driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if completed.returncode == 0:
                    devices = []
                    for line in completed.stdout.splitlines():
                        parts = [part.strip() for part in line.split(",")]
                        if not parts or not parts[0]:
                            continue
                        devices.append(
                            {
                                "index": int(parts[0]) if parts[0].isdigit() else len(devices),
                                "name": parts[1] if len(parts) > 1 else "NVIDIA GPU",
                                "driver_version": parts[2] if len(parts) > 2 else None,
                            }
                        )
                    if devices:
                        result.update(available=True, count=len(devices), devices=devices, source="nvidia-smi")
                        return result
            except (OSError, subprocess.SubprocessError, ValueError):
                pass

        if Path("/dev/nvidia0").exists() or os.environ.get("NVIDIA_VISIBLE_DEVICES") not in {None, "", "void", "none"}:
            result.update(
                available=True,
                count=1,
                devices=[{"index": 0, "name": "NVIDIA GPU", "driver_version": None}],
                source="device",
            )
        return result

    def _candidate_path(self, name: str, bin_dir: Path | None) -> str | None:
        candidate = Path(name)
        if candidate.is_absolute():
            return str(candidate) if candidate.exists() else None
        if bin_dir is not None:
            path = bin_dir / name
            if path.exists():
                return str(path)
        return self._resolve_command(name)

    def detect_dualsphysics(self) -> SolverRuntime:
        demo_mode = bool(getattr(self.settings, "demo_mode", False))
        bin_dir = self.settings.dual_sph_bin_dir
        if bin_dir is None and Path("/opt/dualsphysics/bin").is_dir():
            bin_dir = Path("/opt/dualsphysics/bin")

        names = {
            "gencase": self.settings.dual_sph_gencase or "GenCase_linux64",
            "gpu": self.settings.dual_sph_solver_gpu or "DualSPHysics5.4_linux64",
            "cpu": self.settings.dual_sph_solver_cpu or "DualSPHysics5.4CPU_linux64",
            "partvtk": self.settings.dual_sph_partvtk or "PartVTK_linux64",
        }
        resolved = {key: self._candidate_path(name, bin_dir) for key, name in names.items()}
        gpu = self._detect_gpu()
        cpu_ready = bool(resolved["gencase"] and resolved["cpu"] and resolved["partvtk"])
        gpu_ready = bool(resolved["gencase"] and resolved["gpu"] and resolved["partvtk"] and gpu["available"])
        requested = self.settings.dual_sph_device
        effective = None
        warnings: list[str] = []
        if requested == SphExecutionDevice.GPU.value and gpu_ready:
            effective = SphExecutionDevice.GPU.value
        elif cpu_ready:
            effective = SphExecutionDevice.CPU.value
            if requested == SphExecutionDevice.GPU.value:
                if not gpu["available"]:
                    warnings.append("DualSPHysics GPU mode requested but no NVIDIA GPU is visible; using CPU fallback.")
                else:
                    warnings.append("DualSPHysics GPU executable is unavailable; using CPU fallback.")
        binaries_present = bool(resolved["gencase"] and resolved["gpu"] and resolved["partvtk"])
        if not (cpu_ready or gpu_ready):
            if binaries_present and not gpu["available"]:
                warnings.append(
                    "DualSPHysics binaries are installed, but no NVIDIA GPU is visible inside the container; "
                    "start with run.ps1 or docker-compose.gpu.yml, or provide a CPU runtime."
                )
            else:
                warnings.append("DualSPHysics runtime is unavailable; install/provision GenCase, a solver, and PartVTK.")

        version = "5.4.3" if any(
            "DualSPHysics5.4" in str(value) for value in resolved.values() if value
        ) else None
        if demo_mode and not (cpu_ready or gpu_ready):
            # Keep the automatic browser workflow available when native binaries are
            # absent, but do not mask native installations: when binaries are present,
            # the orchestration layer will execute the real runtime automatically.
            return SolverRuntime(
                key="sph",
                ready=True,
                available=True,
                version="5.4.3",
                device=self.settings.dual_sph_device,
                effective_device="cpu",
                runner_mode=None,
                binaries={"gencase": None, "gpu": None, "cpu": None, "partvtk": None},
                gpu=gpu,
                warnings=[],
            )
        return SolverRuntime(
            key="sph",
            ready=bool(cpu_ready or gpu_ready),
            available=bool(cpu_ready or gpu_ready),
            version=version,
            device=requested,
            effective_device=effective,
            runner_mode=None,
            binaries=resolved,
            gpu=gpu,
            warnings=warnings,
        )

    def detect_delft3d(self) -> SolverRuntime:
        bin_dir = self.settings.delft3d_bin_dir
        configured = self.settings.delft3d_executable or None
        dimr_candidates = ["dimr", "run_dimr.sh", "run_dimr", "dimr.exe"]
        dflow_candidates = ["dflowfm", "dflowfm.exe"]

        def first(candidates: list[str]) -> str | None:
            if configured:
                explicit = self._candidate_path(configured, bin_dir)
                if explicit:
                    return explicit
            for candidate in candidates:
                found = self._candidate_path(candidate, bin_dir)
                if found:
                    return found
            return None

        dimr = first(dimr_candidates)
        dflow = None
        # Do not reuse the configured explicit command for the alternate runner.
        for candidate in dflow_candidates:
            found = self._candidate_path(candidate, bin_dir)
            if found:
                dflow = found
                break

        if dimr:
            mode = Delft3DRunnerMode.DIMR.value
            selected = dimr
        elif dflow:
            mode = Delft3DRunnerMode.DFLOWFM.value
            selected = dflow
        else:
            mode = None
            selected = None

        warnings = [] if selected else [
            "Delft3D FM runtime is unavailable; configure DIMR or dflowfm in the solver runtime directory."
        ]
        return SolverRuntime(
            key="delft3d",
            ready=bool(selected),
            available=bool(selected),
            version=None,
            device=None,
            effective_device=None,
            runner_mode=mode,
            binaries={"dimr": dimr, "dflowfm": dflow, "runner": selected},
            gpu={"available": False, "count": 0, "devices": [], "source": None},
            warnings=warnings,
        )

    def detect(self) -> dict[str, SolverRuntime]:
        return {"sph": self.detect_dualsphysics(), "delft3d": self.detect_delft3d()}
