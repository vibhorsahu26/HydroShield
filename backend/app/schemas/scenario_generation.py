from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.scenarios import SimulationModel


class ScenarioPreset(str, Enum):
    PARTIAL_BREACH = "partial_breach"
    MAJOR_BREACH = "major_breach"
    EXTREME_BREACH = "extreme_breach"
    CONTROLLED_RELEASE = "controlled_release"


class ReleaseMode(str, Enum):
    DAM_BREACH = "dam_breach"
    CONTROLLED_RELEASE = "controlled_release"


class ScenarioGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presets: list[ScenarioPreset] = Field(min_length=1, max_length=4)
    controlled_release_discharge_m3s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_generation_request(self) -> "ScenarioGenerationConfig":
        if len(set(self.presets)) != len(self.presets):
            raise ValueError("presets must not contain duplicates.")
        if ScenarioPreset.CONTROLLED_RELEASE in self.presets and self.controlled_release_discharge_m3s is None:
            raise ValueError(
                "controlled_release_discharge_m3s is required when controlled_release is requested."
            )
        return self


class ScenarioVariantParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_mode: ReleaseMode
    model: SimulationModel
    initial_reservoir_water_level_m: float = Field(gt=0)
    reservoir_volume_m3: float = Field(gt=0)
    breach_width_m: float | None = Field(default=None, gt=0)
    breach_depth_m: float | None = Field(default=None, gt=0)
    breach_formation_time_s: float | None = Field(default=None, gt=0)
    initial_discharge_m3s: float = Field(ge=0)
    controlled_release_discharge_m3s: float | None = Field(default=None, ge=0)
    simulation_duration_s: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_mode(self) -> "ScenarioVariantParameters":
        if self.release_mode == ReleaseMode.DAM_BREACH:
            if self.breach_width_m is None or self.breach_depth_m is None or self.breach_formation_time_s is None:
                raise ValueError("Dam-breach variants require breach width, depth, and formation time.")
            if self.breach_depth_m > self.initial_reservoir_water_level_m:
                raise ValueError("breach_depth_m cannot exceed initial_reservoir_water_level_m.")
            if self.breach_formation_time_s > self.simulation_duration_s:
                raise ValueError("breach_formation_time_s cannot exceed simulation_duration_s.")
            if self.controlled_release_discharge_m3s is not None:
                raise ValueError("Controlled release discharge must be null for dam-breach variants.")
        else:
            if self.breach_width_m is not None or self.breach_depth_m is not None or self.breach_formation_time_s is not None:
                raise ValueError("Controlled-release variants must not contain breach parameters.")
            if self.controlled_release_discharge_m3s is None:
                raise ValueError("Controlled-release variants require a release discharge.")
            if self.initial_discharge_m3s != 0:
                raise ValueError("Controlled-release variants use initial_discharge_m3s=0; use controlled_release_discharge_m3s for release flow.")
        return self


class ScenarioVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    kind: ReleaseMode
    preset: str = Field(min_length=1, max_length=80)
    breach_fraction: float | None = Field(default=None, gt=0, le=1)
    model: SimulationModel
    parameters: dict
    assumptions: dict


class ScenarioGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_scenario_id: str
    generator_version: str
    variants: list[ScenarioVariant]
