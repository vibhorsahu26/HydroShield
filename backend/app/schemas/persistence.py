from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.datasets import DatasetType


class DatasetRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_type: DatasetType
    filename: str = Field(min_length=1, max_length=255)
    storage_uri: str = Field(min_length=1)
    format: str = Field(min_length=1, max_length=32)
    validation_status: Literal["validated", "rejected", "pending"] = "validated"
    crs: str | None = None
    geometry_types: list[str] = Field(default_factory=list)
    shape: list[int] | None = None
    bounds: list[float] | None = None
    feature_count: int | None = Field(default=None, ge=0)
    columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    acquisition_run_id: str | None = None
    provider: str | None = None
    source_url: str | None = None
    source_id: str | None = None
    checksum_sha256: str | None = None
    license: str | None = None
    source_metadata: dict = Field(default_factory=dict)


class DatasetRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    dataset_type: str
    filename: str
    storage_uri: str
    format: str
    validation_status: str
    crs: str | None
    geometry_types: list[str]
    shape: list[int] | None
    bounds: list[float] | None
    feature_count: int | None
    columns: list[str]
    warnings: list[str]
    errors: list[str]
    acquisition_run_id: str | None
    provider: str | None
    source_url: str | None
    source_id: str | None
    checksum_sha256: str | None
    license: str | None
    acquired_at: datetime | None
    source_metadata: dict
    created_at: datetime


class ScenarioRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    model: str
    config: dict
    created_at: datetime
