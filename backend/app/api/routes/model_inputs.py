from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.repositories.projects import ProjectRepository
from app.database.session import get_db
from app.schemas.model_inputs import ModelInputUploadResponse
from app.services.model_input_storage import ModelInputStorageService

router = APIRouter(prefix="/projects", tags=["model-inputs"])
projects = ProjectRepository()


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Model input package exceeds the configured upload limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/{project_id}/model-inputs", response_model=ModelInputUploadResponse, status_code=201)
async def upload_model_inputs(
    project_id: str,
    model: str = Form(..., pattern="^(sph|delft3d)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ModelInputUploadResponse:
    if projects.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    settings = get_settings()
    try:
        data = await _read_limited(file, getattr(settings, "max_upload_bytes", 50 * 1024 * 1024))
        directory, files = ModelInputStorageService(get_settings().model_work_dir).store_zip(
            project_id, model, file.filename or "", data
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModelInputUploadResponse(
        project_id=project_id,
        model=model,
        filename=file.filename or "model-input.zip",
        native_input_directory=str(Path(directory).resolve()),
        files=files,
    )
