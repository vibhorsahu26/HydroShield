from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SimulationModel(str, Enum):
    SPH = "sph"
    DELFT3D = "delft3d"
    BOTH = "both"


class ScenarioConfig(BaseModel):
    """Validated scenario contract shared by API and future execution engines."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    initial_reservoir_water_level_m: float = Field(gt=0)
    reservoir_volume_m3: float = Field(gt=0)
    breach_width_m: float = Field(gt=0)
    breach_depth_m: float = Field(gt=0)
    breach_formation_time_s: float = Field(gt=0)
    initial_discharge_m3s: float = Field(ge=0)
    simulation_duration_s: float = Field(gt=0)
    model: SimulationModel

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must contain non-whitespace characters")
        return value

    @model_validator(mode="after")
    def validate_physics_contract(self) -> "ScenarioConfig":
        if self.breach_depth_m > self.initial_reservoir_water_level_m:
            raise ValueError(
                "breach_depth_m cannot exceed initial_reservoir_water_level_m"
            )
        if self.breach_formation_time_s > self.simulation_duration_s:
            raise ValueError(
                "breach_formation_time_s cannot exceed simulation_duration_s"
            )
        return self


class ScenarioValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    normalized_scenario: ScenarioConfig
