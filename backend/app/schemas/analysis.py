from __future__ import annotations

from enum import Enum
from typing import Any
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComparisonType(str, Enum):
    MODEL = "model"
    SCENARIO = "scenario"


class ResultAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    water_depth_raster: str = Field(min_length=1)
    velocity_raster: str | None = None
    arrival_time_raster: str | None = None
    water_level_raster: str | None = None
    dem_raster: str | None = None
    discharge_csv: str | None = None
    flood_threshold_m: float = Field(default=0.05, ge=0.0, le=100.0)
    output_directory: str | None = None
    exposure_layers: dict[str, str] = Field(default_factory=dict)

    @field_validator("exposure_layers")
    @classmethod
    def validate_layer_names(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("At most 20 exposure layers may be supplied.")
        return value


class AnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    simulation_job_id: str
    project_id: str
    scenario_id: str
    variant_id: str
    analysis_version: str
    flood_threshold_m: float
    metrics: dict[str, Any]
    exposure: dict[str, Any]
    artifacts: dict[str, str]
    warnings: list[str]
    assumptions: dict[str, Any]
    created_at: datetime


class ResultComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_analysis_id: str = Field(min_length=1)
    right_analysis_id: str = Field(min_length=1)
    comparison_type: ComparisonType
    output_directory: str | None = None


class ResultComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    left_analysis_id: str
    right_analysis_id: str
    comparison_type: str
    metrics: dict[str, Any]
    artifacts: dict[str, str]
    warnings: list[str]
    assumptions: dict[str, Any]
    created_at: datetime


class DemoComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_analysis_id: str = Field(min_length=1)
    preferred_preset: str | None = Field(default=None, min_length=1, max_length=64)


class DemoComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_id: str
    scenario_id: str
    source_analysis_id: str
    comparison_variant_id: str
    comparison_variant_code: str
    comparison_variant_preset: str
    simulation_job_id: str
    model: str
    status: str
    prototype: bool

class NativeResultProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flood_threshold_m: float = Field(default=0.05, ge=0.0, le=100.0)
    force: bool = False
