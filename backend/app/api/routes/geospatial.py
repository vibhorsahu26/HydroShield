from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.geospatial.preprocessing import preprocess_geospatial
from app.schemas.geospatial import GeospatialPreprocessConfig, GeospatialPreprocessResponse

router = APIRouter(prefix="/geospatial", tags=["geospatial"])


@router.post("/preprocess", response_model=GeospatialPreprocessResponse)
async def preprocess_uploaded_datasets(
    dem: UploadFile = File(...),
    river: UploadFile = File(...),
    target_crs: str | None = Form(default=None),
    resolution_m: float = Form(default=30.0),
    river_buffer_m: float = Form(default=1000.0),
    min_domain_area_m2: float = Form(default=1.0),
) -> GeospatialPreprocessResponse:
    if not dem.filename or not river.filename:
        raise HTTPException(status_code=400, detail="Both DEM and river filenames are required.")

    try:
        config = GeospatialPreprocessConfig(
            target_crs=target_crs,
            resolution_m=resolution_m,
            river_buffer_m=river_buffer_m,
            min_domain_area_m2=min_domain_area_m2,
        )
        dem_data = await dem.read()
        river_data = await river.read()
        settings = get_settings()
        return preprocess_geospatial(
            dem_data,
            dem.filename,
            river_data,
            river.filename,
            config,
            settings.processing_work_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
