from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.datasets import DatasetType, DatasetValidationResult
from app.services.dataset_validator import validate_dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/validate", response_model=DatasetValidationResult)
async def validate_uploaded_dataset(
    dataset_type: DatasetType = Form(...),
    file: UploadFile = File(...),
) -> DatasetValidationResult:
    data = await file.read()
    try:
        return validate_dataset(data, file.filename or "", dataset_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
