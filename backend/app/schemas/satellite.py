from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SatelliteSensor(str, Enum):
    SENTINEL1 = "sentinel1"
    SENTINEL2 = "sentinel2"


class ObservationPhase(str, Enum):
    BEFORE = "before"
    DURING = "during"
    AFTER = "after"


class SatelliteValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_result_id: str = Field(min_length=1)
    sensor: SatelliteSensor = SatelliteSensor.SENTINEL1
    phase: ObservationPhase = ObservationPhase.DURING
    start_date: date
    end_date: date
    output_directory: str | None = None
    scale_m: float = Field(default=30.0, gt=0, le=1000)
    sentinel2_cloud_pct: float = Field(default=60.0, ge=0, le=100)
    sentinel2_mndwi_threshold: float = Field(default=0.20, ge=-1, le=1)
    temporal_reducer: str = Field(default="max", pattern="^(max|mode)$")

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, value: date, info):
        start = info.data.get("start_date")
        if start and value <= start:
            raise ValueError("end_date must be later than start_date.")
        return value


class SatelliteSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    sensor: SatelliteSensor
    collection_id: str
    image_count: int
    date_start: date
    date_end: date
    selected_image_ids: list[str]
    roi_bounds: list[float]
    processing_method: str
    warnings: list[str] = Field(default_factory=list)


class SatelliteValidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    simulation_job_id: str
    analysis_result_id: str
    project_id: str
    scenario_id: str
    variant_id: str
    sensor: str
    phase: str
    collection_id: str
    start_date: date
    end_date: date
    image_count: int
    selected_image_ids: list[str]
    metrics: dict[str, Any]
    observed_extent_path: str
    difference_map_path: str
    metadata: dict[str, Any] = Field(validation_alias="source_metadata", serialization_alias="metadata")
    warnings: list[str]
    assumptions: dict[str, Any]
    created_at: datetime
