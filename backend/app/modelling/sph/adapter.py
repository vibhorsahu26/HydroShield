from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from app.modelling.base import ExecutionResult, ModelAdapter, PreparedModel
from app.modelling.runner import CommandRunner
from app.modelling.schemas import SphExecutionDevice
from app.modelling.sph.input_builder import ADAPTER_VERSION, build_inputs
from app.modelling.sph.parser import parse_results
from app.schemas.scenarios import SimulationModel


class DualSPHysicsAdapter(ModelAdapter):
    """HydroShield adapter for the DualSPHysics 5.4.3 toolchain."""

    model = SimulationModel.SPH
    adapter_version = ADAPTER_VERSION
    supports_native_result_processing = True

    def __init__(
        self,
        *,
        bin_dir: Path | None = None,
        device: SphExecutionDevice = SphExecutionDevice.GPU,
        gpu_id: int = 0,
        gencase_executable: str | Sequence[str] | None = None,
        solver_gpu_executable: str | Sequence[str] | None = None,
        solver_cpu_executable: str | Sequence[str] | None = None,
        partvtk_executable: str | Sequence[str] | None = None,
        output_interval_s: float = 1.0,
        case_filename: str = "Case_Def.xml",
    ):
        self.bin_dir = bin_dir
        self.device = device
        self.gpu_id = gpu_id
        self.gencase_executable = gencase_executable
        self.solver_gpu_executable = solver_gpu_executable
        self.solver_cpu_executable = solver_cpu_executable
        self.partvtk_executable = partvtk_executable
        self.output_interval_s = output_interval_s
        self.case_filename = case_filename
        self.runner = CommandRunner()

    def prepare(
        self,
        *,
        variant_parameters: dict[str, Any],
        native_input_directory: Path,
        working_directory: Path,
        preprocessing_artifacts: dict[str, str | None] | None = None,
    ) -> PreparedModel:
        return build_inputs(
            variant_parameters=variant_parameters,
            native_input_directory=native_input_directory,
            working_directory=working_directory,
            preprocessing_artifacts=preprocessing_artifacts,
            case_filename=self.case_filename,
            device=self.device,
            gpu_id=self.gpu_id,
            output_interval_s=self.output_interval_s,
            bin_dir=self.bin_dir,
            gencase_executable=self.gencase_executable,
            solver_gpu_executable=self.solver_gpu_executable,
            solver_cpu_executable=self.solver_cpu_executable,
            partvtk_executable=self.partvtk_executable,
        )

    def execute(
        self,
        prepared: PreparedModel,
        *,
        timeout_s: float,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ExecutionResult:
        return self.runner.run(
            prepared,
            adapter=self,
            timeout_s=timeout_s,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def parse_result(self, working_directory: Path):
        return parse_results(working_directory)


# Keep the historical import name stable for existing application callers.
SPHAdapter = DualSPHysicsAdapter
