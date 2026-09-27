from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DatasetType(str, Enum):
    DEM = "dem"
    RIVER = "river"
    DAM = "dam"
    HYDROLOGY = "hydrology"
    RAINFALL = "rainfall"
    LANDCOVER = "landcover"
    SATELLITE = "satellite"
    INFRASTRUCTURE = "infrastructure"
    SETTLEMENT = "settlement"


class DatasetValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    dataset_type: DatasetType
    filename: str = Field(min_length=1)
    format: str
    crs: str | None = None
    geometry_types: list[str] = Field(default_factory=list)
    shape: tuple[int, ...] | None = None
    bounds: tuple[float, float, float, float] | None = None
    feature_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
