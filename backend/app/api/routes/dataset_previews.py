from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.repositories.datasets import DatasetRepository
from app.database.repositories.projects import ProjectRepository
from app.database.session import get_db
from app.schemas.datasets import DatasetType
from app.exports.preview import build_raster_preview

router = APIRouter(prefix="/projects", tags=["dataset-previews"])
projects = ProjectRepository()
datasets = DatasetRepository()

_ALLOWED_RASTER_TYPES = {
    DatasetType.DEM.value,
    DatasetType.LANDCOVER.value,
    DatasetType.SATELLITE.value,
}

_ALLOWED_VECTOR_TYPES = {
    DatasetType.RIVER.value,
    DatasetType.DAM.value,
    DatasetType.SETTLEMENT.value,
    DatasetType.INFRASTRUCTURE.value,
}


def _safe_storage_path(storage_uri: str, root: Path) -> Path:
    path = Path(storage_uri).resolve()
    root = root.resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=403, detail="Dataset storage path is outside the configured storage root.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Dataset file is not available.")
    return path


@router.get("/{project_id}/datasets/{dataset_id}/preview")
def preview_dataset(
    project_id: str,
    dataset_id: str,
    logical_type: str | None = Query(default=None, max_length=64),
    max_features: int = Query(default=3000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    if projects.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    record = datasets.get(db, dataset_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if record.dataset_type not in _ALLOWED_VECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Only vector datasets can be previewed on the map.")
    if logical_type and str((record.source_metadata or {}).get("logical_type") or "") != logical_type:
        raise HTTPException(status_code=404, detail="Dataset logical type does not match the requested preview.")

    path = _safe_storage_path(record.storage_uri, get_settings().storage_root)
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Dataset could not be opened for preview: {exc}") from exc
    if gdf.empty:
        return {"type": "FeatureCollection", "features": [], "crs": "EPSG:4326"}
    if gdf.crs is None:
        raise HTTPException(status_code=422, detail="Dataset has no CRS and cannot be safely previewed.")
    if len(gdf) > max_features:
        gdf = gdf.head(max_features).copy()
    gdf = gdf.to_crs("EPSG:4326")
    geojson = json.loads(gdf.to_json(drop_id=False, default=str))
    return geojson


@router.get("/{project_id}/datasets/{dataset_id}/raster-preview")
def preview_raster_dataset(
    project_id: str,
    dataset_id: str,
    db: Session = Depends(get_db),
):
    """Return a web-safe PNG preview and geographic bounds for a raster dataset."""
    if projects.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    record = datasets.get(db, dataset_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if record.dataset_type not in _ALLOWED_RASTER_TYPES:
        raise HTTPException(status_code=400, detail="Only raster datasets can be previewed with this endpoint.")
    path = _safe_storage_path(record.storage_uri, get_settings().storage_root)
    preview_root = Path(get_settings().export_root) / "dataset-previews" / project_id / dataset_id
    output = preview_root / "preview.png"
    try:
        bounds, metadata = build_raster_preview(path, output, mask=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "dataset_id": dataset_id,
        "dataset_type": record.dataset_type,
        "image_path": f"/projects/{project_id}/datasets/{dataset_id}/raster-preview/image",
        "bounds": bounds,
        "metadata": metadata,
    }


@router.get("/{project_id}/datasets/{dataset_id}/raster-preview/image")
def preview_raster_dataset_image(
    project_id: str,
    dataset_id: str,
    db: Session = Depends(get_db),
):
    record = datasets.get(db, dataset_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if record.dataset_type not in _ALLOWED_RASTER_TYPES:
        raise HTTPException(status_code=400, detail="Only raster datasets can be previewed with this endpoint.")
    path = _safe_storage_path(record.storage_uri, get_settings().storage_root)
    preview_root = Path(get_settings().export_root) / "dataset-previews" / project_id / dataset_id
    output = preview_root / "preview.png"
    if not output.exists():
        try:
            build_raster_preview(path, output, mask=False)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    from fastapi.responses import FileResponse
    return FileResponse(output, media_type="image/png", filename=output.name)
