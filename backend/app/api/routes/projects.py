from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.repositories.datasets import DatasetRepository
from app.database.repositories.scenarios import ScenarioRepository
from app.database.session import get_db
from app.schemas.persistence import DatasetRecordCreate, DatasetRecordResponse, ScenarioRecordResponse
from app.schemas.persistence_variants import ScenarioVariantRecordResponse
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioGenerationResponse
from app.schemas.projects import ProjectCreate, ProjectResponse
from app.schemas.scenarios import ScenarioConfig
from app.services.project_service import ProjectService
from app.services.persistence_service import PersistenceService
from app.services.scenario_service import ScenarioService

router = APIRouter(prefix="/projects", tags=["projects"])
project_service = ProjectService()
persistence_service = PersistenceService()
dataset_repository = DatasetRepository()
scenario_repository = ScenarioRepository()
scenario_service = ScenarioService()


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    return project_service.create(db, payload.name, payload.description)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    return project_service.get(db, project_id)


@router.post("/{project_id}/datasets", response_model=DatasetRecordResponse, status_code=201)
def create_dataset_record(
    project_id: str,
    payload: DatasetRecordCreate,
    db: Session = Depends(get_db),
) -> DatasetRecordResponse:
    return persistence_service.create_dataset(db, project_id, **payload.model_dump())


@router.get("/{project_id}/datasets", response_model=list[DatasetRecordResponse])
def list_project_datasets(project_id: str, db: Session = Depends(get_db)) -> list[DatasetRecordResponse]:
    project_service.get(db, project_id)
    return dataset_repository.list_for_project(db, project_id)


@router.post("/{project_id}/scenarios", response_model=ScenarioRecordResponse, status_code=201)
def create_scenario_record(
    project_id: str,
    payload: ScenarioConfig,
    db: Session = Depends(get_db),
) -> ScenarioRecordResponse:
    return persistence_service.create_scenario(
        db,
        project_id,
        name=payload.name,
        model=payload.model.value,
        config=payload.model_dump(mode="json"),
    )


@router.get("/{project_id}/scenarios", response_model=list[ScenarioRecordResponse])
def list_project_scenarios(project_id: str, db: Session = Depends(get_db)) -> list[ScenarioRecordResponse]:
    project_service.get(db, project_id)
    return scenario_repository.list_for_project(db, project_id)


@router.post(
    "/{project_id}/scenarios/{scenario_id}/variants/generate",
    response_model=ScenarioGenerationResponse,
    status_code=201,
)
def generate_scenario_variants_for_project(
    project_id: str,
    scenario_id: str,
    payload: ScenarioGenerationConfig,
    db: Session = Depends(get_db),
) -> ScenarioGenerationResponse:
    return scenario_service.generate_variants(
        db,
        project_id=project_id,
        scenario_id=scenario_id,
        config=payload,
    )


@router.get(
    "/{project_id}/scenarios/{scenario_id}/variants",
    response_model=list[ScenarioVariantRecordResponse],
)
def list_scenario_variants(
    project_id: str,
    scenario_id: str,
    db: Session = Depends(get_db),
) -> list[ScenarioVariantRecordResponse]:
    return scenario_service.list_variants(
        db, project_id=project_id, scenario_id=scenario_id
    )
