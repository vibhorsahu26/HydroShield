from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.scenarios import ScenarioConfig, SimulationModel
from app.schemas.scenario_generation import (
    ScenarioGenerationConfig,
    ScenarioPreset,
    ScenarioVariant,
    ScenarioVariantParameters,
)

GENERATOR_VERSION = "1.0"

_PRESET_FRACTIONS = {
    ScenarioPreset.PARTIAL_BREACH: 0.25,
    ScenarioPreset.MAJOR_BREACH: 0.50,
    ScenarioPreset.EXTREME_BREACH: 1.00,
}


@dataclass(frozen=True)
class GeneratedVariant:
    code: str
    kind: str
    preset: str
    breach_fraction: float | None
    parameters: dict[str, Any]
    assumptions: dict[str, Any]


def _scaled(value: float, fraction: float) -> float:
    return value * fraction


def _breach_variant(base: ScenarioConfig, preset: ScenarioPreset) -> GeneratedVariant:
    fraction = _PRESET_FRACTIONS[preset]
    parameters = ScenarioVariantParameters(
        release_mode="dam_breach",
        model=base.model,
        initial_reservoir_water_level_m=base.initial_reservoir_water_level_m,
        reservoir_volume_m3=base.reservoir_volume_m3,
        breach_width_m=_scaled(base.breach_width_m, fraction),
        breach_depth_m=_scaled(base.breach_depth_m, fraction),
        breach_formation_time_s=base.breach_formation_time_s,
        initial_discharge_m3s=_scaled(base.initial_discharge_m3s, fraction),
        controlled_release_discharge_m3s=None,
        simulation_duration_s=base.simulation_duration_s,
    )
    assumptions = {
        "generator_version": GENERATOR_VERSION,
        "scaling_policy": "linear_breach_and_release",
        "scaling_policy_description": (
            "Preset fraction is applied linearly to breach width, breach depth, and initial discharge. "
            "Reservoir conditions, breach formation time, and simulation duration remain unchanged. "
            "This is a transparent scenario-construction convention, not a hydraulic solver law."
        ),
        "base_scenario_name": base.name,
        "model_inherited_from_base": base.model.value,
    }
    labels = {
        ScenarioPreset.PARTIAL_BREACH: "Partial Breach",
        ScenarioPreset.MAJOR_BREACH: "Major Breach",
        ScenarioPreset.EXTREME_BREACH: "Extreme Breach",
    }
    return GeneratedVariant(
        code=preset.value,
        kind="dam_breach",
        preset=labels[preset],
        breach_fraction=fraction,
        parameters=parameters.model_dump(mode="json"),
        assumptions=assumptions,
    )


def _controlled_variant(
    base: ScenarioConfig,
    discharge_m3s: float,
) -> GeneratedVariant:
    parameters = ScenarioVariantParameters(
        release_mode="controlled_release",
        model=base.model,
        initial_reservoir_water_level_m=base.initial_reservoir_water_level_m,
        reservoir_volume_m3=base.reservoir_volume_m3,
        breach_width_m=None,
        breach_depth_m=None,
        breach_formation_time_s=None,
        initial_discharge_m3s=0.0,
        controlled_release_discharge_m3s=discharge_m3s,
        simulation_duration_s=base.simulation_duration_s,
    )
    assumptions = {
        "generator_version": GENERATOR_VERSION,
        "scaling_policy": "none",
        "controlled_release_discharge_source": "explicit_user_input",
        "model_inherited_from_base": base.model.value,
    }
    return GeneratedVariant(
        code=ScenarioPreset.CONTROLLED_RELEASE.value,
        kind="controlled_release",
        preset="Controlled Water Release",
        breach_fraction=None,
        parameters=parameters.model_dump(mode="json"),
        assumptions=assumptions,
    )


def generate_scenario_variants(
    base: ScenarioConfig,
    config: ScenarioGenerationConfig,
) -> list[ScenarioVariant]:
    if not config.presets:
        raise ValueError("At least one scenario preset must be requested.")

    variants: list[GeneratedVariant] = []
    for preset in config.presets:
        if preset == ScenarioPreset.CONTROLLED_RELEASE:
            if config.controlled_release_discharge_m3s is None:
                raise ValueError(
                    "controlled_release_discharge_m3s is required when controlled_release is requested."
                )
            variants.append(_controlled_variant(base, config.controlled_release_discharge_m3s))
        else:
            variants.append(_breach_variant(base, preset))

    return [
        ScenarioVariant(
            code=item.code,
            kind=item.kind,
            preset=item.preset,
            breach_fraction=item.breach_fraction,
            model=base.model,
            parameters=item.parameters,
            assumptions=item.assumptions,
        )
        for item in variants
    ]
