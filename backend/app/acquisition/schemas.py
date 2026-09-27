from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DamSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=200)
    country_code: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")


class DamCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    osm_type: str | None = None
    osm_id: int | None = None
    category: str | None = None
    object_type: str | None = None
    river_name: str | None = None


class DamSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    candidates: list[DamCandidate]
    attribution: str = "© OpenStreetMap contributors"
    provider: str = "OpenStreetMap Nominatim"


class AutomaticAcquisitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dam_name: str = Field(min_length=1, max_length=160)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=10.0, gt=0, le=25)
    river_name: str | None = Field(default=None, max_length=160)
    dem_resolution: str = Field(default="auto", pattern=r"^(auto|30m|90m)$")
    include_exposure: bool = True
    auto_preprocess: bool = True


class AcquiredDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    dataset_type: str
    logical_type: str | None = None
    filename: str
    provider: str
    source: str
    source_id: str | None = None
    status: str
    storage_uri: str | None = None
    checksum_sha256: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AutomaticAcquisitionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acquisition_run_id: str
    project_id: str
    dam_name: str
    latitude: float
    longitude: float
    radius_km: float
    bbox_wgs84: tuple[float, float, float, float]
    datasets: list[AcquiredDataset]
    preprocessing: dict | None = None
    warnings: list[str] = Field(default_factory=list)
    attribution: list[str] = Field(default_factory=lambda: ["© OpenStreetMap contributors"])


class AcquisitionRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    status: str
    request: dict
    provider_summary: dict
    warnings: list[str]
    error_message: str | None
