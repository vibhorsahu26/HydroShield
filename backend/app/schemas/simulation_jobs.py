from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.modelling.schemas import ModelPrepareRequest
from app.modelling.base import ExecutionResult


class SimulationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    model: str = Field(pattern="^(sph|delft3d)$")
    prepare: ModelPrepareRequest
    max_attempts: int = Field(default=1, ge=1, le=5)


class SimulationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    scenario_id: str
    variant_id: str
    model: str
    status: str
    progress: float
    current_step: str
    attempt: int
    max_attempts: int
    timeout_s: float
    config: dict
    working_directory: str | None = None
    manifest_path: str | None = None
    error_message: str | None = None
    result: dict | None = None
    cancel_requested: bool
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
