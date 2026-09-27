from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @field_validator("max_x")
    @classmethod
    def max_x_after_min_x(cls, value: float, info):
        if "min_x" in info.data and value <= info.data["min_x"]:
            raise ValueError("max_x must be greater than min_x.")
        return value

    @field_validator("max_y")
    @classmethod
    def max_y_after_min_y(cls, value: float, info):
        if "min_y" in info.data and value <= info.data["min_y"]:
            raise ValueError("max_y must be greater than min_y.")
        return value


class GeospatialPreprocessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_crs: str | None = Field(default=None, min_length=3, max_length=64)
    resolution_m: float = Field(default=30.0, gt=0, le=1000)
    river_buffer_m: float = Field(default=1000.0, gt=0, le=100_000)
    min_domain_area_m2: float = Field(default=1.0, gt=0)


class RasterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    crs: str
    width: int
    height: int
    count: int
    resolution_x: float
    resolution_y: float
    nodata: float | None
    bounds: BoundingBox
    valid_cell_count: int


class VectorMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    crs: str
    feature_count: int
    geometry_types: list[str]
    bounds: BoundingBox
    total_length_m: float


class DomainMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    mask_raster_path: str
    crs: str
    area_m2: float
    bounds: BoundingBox
    feature_count: int


class GeospatialPreprocessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processing_crs: str
    processing_crs_name: str
    config: GeospatialPreprocessConfig
    dem: RasterMetadata
    river: VectorMetadata
    domain: DomainMetadata
    warnings: list[str] = Field(default_factory=list)
