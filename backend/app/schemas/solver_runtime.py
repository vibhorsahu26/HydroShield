from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GpuRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    count: int = Field(ge=0)
    devices: list[dict] = Field(default_factory=list)
    source: str | None = None


class SolverRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    available: bool
    version: str | None = None
    device: str | None = None
    effective_device: str | None = None
    runner_mode: str | None = None
    binaries: dict[str, str | None] = Field(default_factory=dict)
    gpu: GpuRuntimeStatus
    warnings: list[str] = Field(default_factory=list)


class SolverPreflightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sph: SolverRuntimeStatus
    delft3d: SolverRuntimeStatus
    checked_at: str
