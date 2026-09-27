from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.repositories.projects import ProjectRepository
from app.modelling.schemas import ModelPrepareRequest
from app.orchestration.manager import SimulationJobManager
from app.orchestration.states import JobStatus
from app.schemas.scenarios import SimulationModel
from app.schemas.simulation_jobs import SimulationJobCreate, SimulationJobResponse

router = APIRouter(prefix="/simulations", tags=["simulations"])
project_repository = ProjectRepository()


def get_job_manager(request: Request) -> SimulationJobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        raise RuntimeError("Simulation job manager is not initialized.")
    return manager


@router.post("", response_model=SimulationJobResponse, status_code=202)
def create_simulation(
    payload: SimulationJobCreate,
    db: Session = Depends(get_db),
    manager: SimulationJobManager = Depends(get_job_manager),
) -> SimulationJobResponse:
    try:
        job = manager.create_and_submit(
            db,
            project_id=payload.project_id,
            scenario_id=payload.scenario_id,
            variant_id=payload.variant_id,
            model=SimulationModel(payload.model),
            prepare=payload.prepare,
            max_attempts=payload.max_attempts,
        )
        return job
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=SimulationJobResponse)
def get_simulation(
    job_id: str,
    db: Session = Depends(get_db),
    manager: SimulationJobManager = Depends(get_job_manager),
) -> SimulationJobResponse:
    job = manager.get(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Simulation job not found.")
    return job


@router.get("/projects/{project_id}", response_model=list[SimulationJobResponse])
def list_project_simulations(
    project_id: str,
    db: Session = Depends(get_db),
    manager: SimulationJobManager = Depends(get_job_manager),
) -> list[SimulationJobResponse]:
    if project_repository.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return manager.list_for_project(db, project_id)


@router.post("/{job_id}/cancel", response_model=SimulationJobResponse)
def cancel_simulation(
    job_id: str,
    db: Session = Depends(get_db),
    manager: SimulationJobManager = Depends(get_job_manager),
) -> SimulationJobResponse:
    try:
        return manager.cancel(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
