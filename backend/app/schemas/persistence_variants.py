from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScenarioVariantRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_scenario_id: str
    code: str
    kind: str
    preset: str
    breach_fraction: float | None
    model: str
    parameters: dict
    assumptions: dict
    created_at: datetime
