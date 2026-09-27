from __future__ import annotations

from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
from app.schemas.scenarios import ScenarioConfig, SimulationModel
from app.scenarios.generator import GENERATOR_VERSION, generate_scenario_variants


def base_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="Base Dam Break",
        initial_reservoir_water_level_m=120,
        reservoir_volume_m3=5_000_000,
        breach_width_m=40,
        breach_depth_m=20,
        breach_formation_time_s=300,
        initial_discharge_m3s=200,
        simulation_duration_s=3600,
        model=SimulationModel.BOTH,
    )


def test_generates_three_breach_presets_with_transparent_scaling():
    result = generate_scenario_variants(
        base_scenario(),
        ScenarioGenerationConfig(
            presets=[
                ScenarioPreset.PARTIAL_BREACH,
                ScenarioPreset.MAJOR_BREACH,
                ScenarioPreset.EXTREME_BREACH,
            ]
        ),
    )

    assert GENERATOR_VERSION == "1.0"
    assert [item.code for item in result] == [
        "partial_breach",
        "major_breach",
        "extreme_breach",
    ]
    assert [item.breach_fraction for item in result] == [0.25, 0.5, 1.0]

    partial = result[0].parameters
    major = result[1].parameters
    extreme = result[2].parameters
    assert partial["breach_width_m"] == 10
    assert partial["breach_depth_m"] == 5
    assert partial["initial_discharge_m3s"] == 50
    assert major["breach_width_m"] == 20
    assert major["breach_depth_m"] == 10
    assert major["initial_discharge_m3s"] == 100
    assert extreme["breach_width_m"] == 40
    assert extreme["breach_depth_m"] == 20
    assert extreme["initial_discharge_m3s"] == 200
    assert all(item.assumptions["generator_version"] == "1.0" for item in result)


def test_controlled_release_requires_explicit_discharge_and_has_no_breach_parameters():
    result = generate_scenario_variants(
        base_scenario(),
        ScenarioGenerationConfig(
            presets=[ScenarioPreset.CONTROLLED_RELEASE],
            controlled_release_discharge_m3s=75,
        ),
    )
    assert len(result) == 1
    variant = result[0]
    assert variant.code == "controlled_release"
    assert variant.kind.value == "controlled_release"
    assert variant.parameters["breach_width_m"] is None
    assert variant.parameters["breach_depth_m"] is None
    assert variant.parameters["controlled_release_discharge_m3s"] == 75
    assert variant.parameters["initial_discharge_m3s"] == 0
    assert variant.assumptions["controlled_release_discharge_source"] == "explicit_user_input"


def test_controlled_release_without_discharge_is_rejected():
    try:
        ScenarioGenerationConfig(presets=[ScenarioPreset.CONTROLLED_RELEASE])
    except ValueError as exc:
        assert "controlled_release_discharge_m3s" in str(exc)
    else:
        raise AssertionError("Expected controlled release discharge to be required")


def test_duplicate_presets_are_rejected():
    try:
        ScenarioGenerationConfig(
            presets=[ScenarioPreset.PARTIAL_BREACH, ScenarioPreset.PARTIAL_BREACH]
        )
    except ValueError as exc:
        assert "duplicates" in str(exc)
    else:
        raise AssertionError("Expected duplicate presets to be rejected")
