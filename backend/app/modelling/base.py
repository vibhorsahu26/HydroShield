from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from app.schemas.scenarios import SimulationModel


@dataclass(frozen=True)
class PreparedModel:
    model: SimulationModel
    adapter_version: str
    working_directory: Path
    manifest_path: Path
    command: list[str]
    execution_steps: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionResult:
    model: SimulationModel
    status: str
    exit_code: int
    duration_s: float
    working_directory: Path
    command: list[str]
    stdout_log: Path
    stderr_log: Path
    artifacts: list[Path] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    step_results: list[dict[str, Any]] = field(default_factory=list)


class ModelAdapter(ABC):
    model: SimulationModel
    adapter_version: str
    supports_native_result_processing: bool = False

    @abstractmethod
    def prepare(
        self,
        *,
        variant_parameters: dict[str, Any],
        native_input_directory: Path,
        working_directory: Path,
        preprocessing_artifacts: dict[str, str | None] | None = None,
    ) -> PreparedModel:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        prepared: PreparedModel,
        *,
        timeout_s: float,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def parse_result(self, working_directory: Path) -> tuple[dict[str, Any] | None, list[Path], list[str]]:
        raise NotImplementedError
