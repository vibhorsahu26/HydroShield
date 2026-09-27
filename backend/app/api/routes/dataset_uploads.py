from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.repositories.projects import ProjectRepository
from app.database.session import get_db
from app.schemas.datasets import DatasetType
from app.schemas.persistence import DatasetRecordResponse
from app.services.dataset_storage import DatasetStorageService
from app.services.persistence_service import PersistenceService

router = APIRouter(prefix="/projects", tags=["datasets"])
project_repository = ProjectRepository()
persistence_service = PersistenceService()


async def _read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured size limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/{project_id}/datasets/upload", response_model=DatasetRecordResponse, status_code=201)
async def upload_dataset(
    project_id: str,
    dataset_type: DatasetType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DatasetRecordResponse:
    if project_repository.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    filename = file.filename or ""
    settings = get_settings()
    try:
        data = await _read_upload(file, getattr(settings, "max_upload_bytes", 50 * 1024 * 1024))
        storage = DatasetStorageService(settings.storage_root)
        validation = storage.validate_and_store(
            project_id, filename, data, dataset_type,
            max_upload_bytes=getattr(settings, "max_upload_bytes", 50 * 1024 * 1024),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    validation_result, stored = validation
    return persistence_service.create_dataset(
        db,
        project_id,
        dataset_type=dataset_type.value,
        filename=filename,
        storage_uri=str(stored.path),
        format=validation_result["format"],
        validation_status="validated",
        crs=validation_result.get("crs"),
        geometry_types=validation_result.get("geometry_types", []),
        shape=list(validation_result["shape"]) if validation_result.get("shape") else None,
        bounds=list(validation_result["bounds"]) if validation_result.get("bounds") else None,
        feature_count=validation_result.get("feature_count"),
        columns=validation_result.get("columns", []),
        warnings=validation_result.get("warnings", []),
        errors=validation_result.get("errors", []),
        acquisition_run_id=None,
        provider="manual_upload",
        source_url=None,
        source_id=None,
        checksum_sha256=stored.sha256,
        license=None,
        source_metadata={"acquisition_method": "manual_upload"},
    )
