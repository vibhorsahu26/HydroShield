from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scenarios import SimulationModel


class ExecutionMode(str, Enum):
    PROTOTYPE = "prototype"
    NATIVE = "native"


class Delft3DRunnerMode(str, Enum):
    DFLOWFM = "dflowfm"
    DIMR = "dimr"


class SphExecutionDevice(str, Enum):
    GPU = "gpu"
    CPU = "cpu"


class ModelPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_mode: ExecutionMode | None = None
    native_input_directory: str | None = Field(default=None, min_length=1)
    auto_generate: bool = False
    working_directory: str | None = None
    solver_executable: str | None = None
    delft3d_runner_mode: Delft3DRunnerMode = Delft3DRunnerMode.DIMR
    sph_device: SphExecutionDevice = SphExecutionDevice.GPU
    sph_gpu_id: int = Field(default=0, ge=0, le=64)
    sph_output_interval_s: float = Field(default=1.0, gt=0)
    sph_case_filename: str = Field(default="Case_Def.xml", min_length=1, max_length=255)
    timeout_s: float = Field(default=3600.0, gt=0, le=86_400)
    preprocessed_dem: str | None = None
    prepared_river: str | None = None
    computational_domain: str | None = None
    domain_mask: str | None = None


class ModelPrepareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: SimulationModel
    adapter_version: str
    working_directory: str
    manifest_path: str
    command: list[str]
    execution_steps: list[list[str]] = Field(default_factory=list)
    native_input_directory: str
    warnings: list[str] = Field(default_factory=list)


class ModelRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_water_depth_m: float | None = None
    max_velocity_mps: float | None = None
    inundated_area_m2: float | None = None
    first_arrival_time_s: float | None = None
    final_max_water_depth_m: float | None = None
    time_steps: int | None = None
    wet_cell_count: int | None = None
    particle_count: int | None = None


class ModelExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: SimulationModel
    status: str
    exit_code: int
    duration_s: float
    working_directory: str
    command: list[str]
    stdout_log: str
    stderr_log: str
    artifacts: list[str] = Field(default_factory=list)
    summary: ModelRunSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    step_results: list[dict] = Field(default_factory=list)
