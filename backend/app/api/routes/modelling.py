from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.modelling.schemas import ModelPrepareRequest, ModelPrepareResponse
from app.modelling.service import ModellingService
from app.schemas.scenarios import SimulationModel

router = APIRouter(prefix="/modelling", tags=["modelling"])
service = ModellingService()


@router.post(
    "/projects/{project_id}/scenarios/{scenario_id}/variants/{variant_id}/prepare/{model}",
    response_model=ModelPrepareResponse,
)
def prepare_model_inputs(
    project_id: str,
    scenario_id: str,
    variant_id: str,
    model: SimulationModel,
    payload: ModelPrepareRequest,
    db: Session = Depends(get_db),
) -> ModelPrepareResponse:
    if model == SimulationModel.BOTH:
        raise ValueError("Preparation requires a concrete model: sph or delft3d.")
    try:
        return service.prepare_variant(
            db,
            project_id=project_id,
            scenario_id=scenario_id,
            variant_id=variant_id,
            model=model,
            config=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
