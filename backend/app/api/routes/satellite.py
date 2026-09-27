from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.satellite.gee import EarthEngineUnavailable
from app.schemas.satellite import SatelliteValidationRequest, SatelliteValidationResponse
from app.services.satellite_service import SatelliteValidationService
from app.exports.preview import build_raster_preview

router = APIRouter(prefix="/satellite", tags=["satellite-validation"])


def get_service() -> SatelliteValidationService:
    return SatelliteValidationService()


@router.post("/validate", response_model=SatelliteValidationResponse, status_code=201)
def validate_satellite(
    payload: SatelliteValidationRequest,
    db: Session = Depends(get_db),
    service: SatelliteValidationService = Depends(get_service),
):
    try:
        return service.validate(db, payload)
    except EarthEngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/validations/{validation_id}", response_model=SatelliteValidationResponse)
def get_satellite_validation(validation_id: str, db: Session = Depends(get_db), service: SatelliteValidationService = Depends(get_service)):
    record = service.repository.get(db, validation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite validation result not found.")
    return record


@router.get("/analyses/{analysis_id}/validations", response_model=list[SatelliteValidationResponse])
def list_satellite_validations(analysis_id: str, db: Session = Depends(get_db), service: SatelliteValidationService = Depends(get_service)):
    return service.repository.list_for_analysis(db, analysis_id)


@router.get("/validations/{validation_id}/observed-extent")
def preview_observed_extent(validation_id: str, db: Session = Depends(get_db), service: SatelliteValidationService = Depends(get_service)):
    record = service.repository.get(db, validation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite validation result not found.")
    source = Path(record.observed_extent_path).resolve()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="Observed satellite extent artifact is not available.")
    try:
        gdf = gpd.read_file(source)
        if gdf.crs is None:
            raise ValueError("Observed extent has no CRS.")
        gdf = gdf.to_crs("EPSG:4326")
        return json.loads(gdf.to_json(drop_id=False, default=str))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Observed satellite extent could not be opened: {exc}") from exc


@router.get("/validations/{validation_id}/difference-preview")
def preview_difference(validation_id: str, db: Session = Depends(get_db), service: SatelliteValidationService = Depends(get_service)):
    record = service.repository.get(db, validation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite validation result not found.")
    source = Path(record.difference_map_path).resolve()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="Satellite difference-map artifact is not available.")
    output = source.parent / "difference_preview.png"
    try:
        bounds, metadata = build_raster_preview(source, output, mask=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"image_path": f"/satellite/validations/{validation_id}/difference-preview/image", "bounds": bounds, "metadata": metadata}


@router.get("/validations/{validation_id}/difference-preview/image")
def preview_difference_image(validation_id: str, db: Session = Depends(get_db), service: SatelliteValidationService = Depends(get_service)):
    record = service.repository.get(db, validation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite validation result not found.")
    source = Path(record.difference_map_path).resolve()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="Satellite difference-map artifact is not available.")
    output = source.parent / "difference_preview.png"
    if not output.exists():
        try:
            build_raster_preview(source, output, mask=False)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(output, media_type="image/png", filename=output.name)
