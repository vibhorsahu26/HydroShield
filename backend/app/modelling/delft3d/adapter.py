from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import shutil

from app.modelling.base import ExecutionResult, ModelAdapter, PreparedModel
from app.modelling.delft3d.input_builder import ADAPTER_VERSION, build_inputs
from app.modelling.delft3d.parser import parse_results
from app.modelling.runner import CommandRunner
from app.modelling.schemas import Delft3DRunnerMode
from app.schemas.scenarios import SimulationModel


class Delft3DAdapter(ModelAdapter):
    model = SimulationModel.DELFT3D
    adapter_version = ADAPTER_VERSION
    supports_native_result_processing = True

    def __init__(
        self,
        *,
        runner_mode: Delft3DRunnerMode = Delft3DRunnerMode.DIMR,
        executable: str = "",
    ):
        self.runner_mode = runner_mode
        self.executable = executable
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
            runner_mode=self.runner_mode,
            executable=self.executable,
            preprocessing_artifacts=preprocessing_artifacts,
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
