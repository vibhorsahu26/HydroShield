from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import SimulationJob
from app.database.session import get_db
from app.schemas.analysis_inputs import AnalysisInputUploadResponse
from app.schemas.datasets import DatasetType
from app.services.analysis_input_storage import AnalysisInputStorageService
from app.services.dataset_validator import validate_dataset

router = APIRouter(prefix="/results", tags=["result-inputs"])
_ALLOWED_FIELDS = {
    "water_depth_raster": ".tif",
    "velocity_raster": ".tif",
    "arrival_time_raster": ".tif",
    "water_level_raster": ".tif",
    "dem_raster": ".tif",
    "discharge_csv": ".csv",
}


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Analysis input exceeds the configured upload limit.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _validate_and_store(service: AnalysisInputStorageService, job_id: str, field: str, upload: UploadFile, max_bytes: int) -> str:
    filename = upload.filename or ""
    if Path(filename).suffix.lower() != _ALLOWED_FIELDS[field]:
        raise HTTPException(status_code=400, detail=f"{field} must be a {_ALLOWED_FIELDS[field]} file.")
    data = await _read_limited(upload, max_bytes)
    dataset_type = DatasetType.HYDROLOGY if field == "discharge_csv" else DatasetType.DEM
    validation = validate_dataset(data, filename, dataset_type, max_upload_bytes=max_bytes)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=f"{field} validation failed: {'; '.join(validation.errors)}")
    return str(service.store(job_id, field, filename, data).resolve())


@router.post("/simulations/{job_id}/analysis-inputs", response_model=AnalysisInputUploadResponse, status_code=201)
async def upload_analysis_inputs(
    job_id: str,
    water_depth_raster: UploadFile = File(...),
    velocity_raster: UploadFile | None = File(default=None),
    arrival_time_raster: UploadFile | None = File(default=None),
    water_level_raster: UploadFile | None = File(default=None),
    dem_raster: UploadFile | None = File(default=None),
    discharge_csv: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> AnalysisInputUploadResponse:
    job = db.get(SimulationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Simulation job not found.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Simulation job must be completed before analysis inputs are uploaded.")
    settings = get_settings()
    service = AnalysisInputStorageService(settings.model_work_dir)
    uploads = {
        "water_depth_raster": water_depth_raster,
        "velocity_raster": velocity_raster,
        "arrival_time_raster": arrival_time_raster,
        "water_level_raster": water_level_raster,
        "dem_raster": dem_raster,
        "discharge_csv": discharge_csv,
    }
    files: dict[str, str] = {}
    for field, upload in uploads.items():
        if upload is not None:
            files[field] = await _validate_and_store(service, job_id, field, upload, getattr(settings, "max_upload_bytes", 50 * 1024 * 1024))
    return AnalysisInputUploadResponse(
        simulation_job_id=job_id,
        directory=str((settings.model_work_dir / "analysis-inputs" / job_id).resolve()),
        files=files,
    )
