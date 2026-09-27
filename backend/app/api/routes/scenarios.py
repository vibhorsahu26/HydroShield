from fastapi import APIRouter

from app.schemas.scenarios import ScenarioConfig, ScenarioValidationResponse

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.post("/validate", response_model=ScenarioValidationResponse)
def validate_scenario(scenario: ScenarioConfig) -> ScenarioValidationResponse:
    """Validate and normalize scenario parameters without starting a simulation."""
    normalized = scenario.model_copy(update={"name": scenario.name.strip()})
    return ScenarioValidationResponse(valid=True, normalized_scenario=normalized)
