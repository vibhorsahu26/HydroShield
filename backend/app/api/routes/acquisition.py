from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.acquisition.manager import AcquisitionManager
from app.acquisition.schemas import (
    AutomaticAcquisitionRequest,
    AutomaticAcquisitionResponse,
    AcquisitionRunResponse,
    DamSearchRequest,
    DamSearchResponse,
)
from app.core.config import get_settings
from app.database.session import get_db
from app.core.errors import NotFoundError
from app.database.repositories.projects import ProjectRepository
from app.database.models import AcquisitionRun
from sqlalchemy import select

router = APIRouter(prefix="/acquisition", tags=["automatic-data-acquisition"])
project_repository = ProjectRepository()


@router.post("/search", response_model=DamSearchResponse)
def search_dams(payload: DamSearchRequest) -> DamSearchResponse:
    settings = get_settings()
    try:
        candidates = AcquisitionManager(settings).search_dams(payload.query, payload.country_code)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return DamSearchResponse(query=payload.query, candidates=candidates)


@router.post("/projects/{project_id}/run", response_model=AutomaticAcquisitionResponse, status_code=201)
def acquire_for_project(
    project_id: str,
    payload: AutomaticAcquisitionRequest,
    db: Session = Depends(get_db),
) -> AutomaticAcquisitionResponse:
    if project_repository.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    manager = AcquisitionManager(get_settings())
    try:
        run, acquired, preprocessing, warnings, bbox = manager.run(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Automatic data acquisition failed: {exc}") from exc
    return AutomaticAcquisitionResponse(
        acquisition_run_id=run.id,
        project_id=project_id,
        dam_name=payload.dam_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_km=payload.radius_km,
        bbox_wgs84=bbox,
        datasets=[
            {
                "dataset_id": item["record"].id,
                "dataset_type": item["record"].dataset_type,
                "logical_type": item["logical_type"],
                "filename": item["record"].filename,
                "provider": item["provider"],
                "source": item["source"],
                "source_id": item["record"].source_id,
                "status": item["record"].validation_status,
                "storage_uri": item["record"].storage_uri,
                "checksum_sha256": item["record"].checksum_sha256,
                "warnings": item["warnings"],
            }
            for item in acquired
        ],
        preprocessing=preprocessing,
        warnings=warnings,
    )


@router.get("/projects/{project_id}/runs", response_model=list[AcquisitionRunResponse])
def list_acquisition_runs(project_id: str, db: Session = Depends(get_db)) -> list[AcquisitionRunResponse]:
    if project_repository.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    stmt = select(AcquisitionRun).where(AcquisitionRun.project_id == project_id).order_by(AcquisitionRun.created_at.desc())
    return list(db.scalars(stmt).all())
