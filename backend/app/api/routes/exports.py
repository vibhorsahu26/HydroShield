from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import AnalysisResult, ResultComparison
from app.database.session import get_db
from app.exports.preview import _ALLOWED, build_raster_preview, sample_raster
from app.exports.flood_zones import build_flood_zones
from app.exports.service import ExportError, build_analysis_package, export_analysis

router = APIRouter(prefix="/exports", tags=["exports"] )


def _result(db: Session, result_id: str) -> AnalysisResult:
    record = db.get(AnalysisResult, result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis result not found.")
    return record


def _comparison(db: Session, comparison_id: str) -> ResultComparison:
    record = db.get(ResultComparison, comparison_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Result comparison not found.")
    return record


def _root() -> Path:
    root = Path(get_settings().export_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.get("/analysis/{result_id}")
def export_analysis_result(
    result_id: str,
    format: str = Query(..., pattern="^(geojson|shp|kml|geotiff|csv|json)$"),
    artifact: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    record = _result(db, result_id)
    try:
        path, media_type = export_analysis(record, format, artifact, _root() / record.id)
    except ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_type, filename=path.name)




@router.get("/analysis/{result_id}/preview")
def preview_analysis_raster(
    result_id: str,
    artifact: str = Query(..., pattern="^(water_depth_raster|flood_mask_raster|velocity_raster|arrival_time_raster|water_level_raster)$"),
    db: Session = Depends(get_db),
):
    record = _result(db, result_id)
    source = record.artifacts.get(_ALLOWED[artifact])
    if not source:
        raise HTTPException(status_code=404, detail=f"Raster artifact '{artifact}' is not available.")
    preview_root = _root() / record.id / "previews"
    output = preview_root / f"{artifact}.png"
    try:
        bounds, metadata = build_raster_preview(source, output, mask=artifact == "flood_mask_raster", artifact=artifact)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "artifact": artifact,
        "image_path": f"/exports/analysis/{record.id}/preview/image?artifact={artifact}",
        "bounds": bounds,
        "metadata": metadata,
    }


@router.get("/analysis/{result_id}/flood-zones")
def preview_flood_zones(result_id: str, db: Session = Depends(get_db)):
    record = _result(db, result_id)
    source = record.artifacts.get("water_depth_raster")
    if not source:
        raise HTTPException(status_code=404, detail="Water-depth raster is not available.")
    try:
        return build_flood_zones(source, flood_threshold_m=float(record.flood_threshold_m or 0.05))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analysis/{result_id}/sample")
def sample_analysis_raster(
    result_id: str,
    artifact: str = Query(..., pattern="^(water_depth_raster|velocity_raster|arrival_time_raster|water_level_raster)$"),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    record = _result(db, result_id)
    source = record.artifacts.get(_ALLOWED[artifact])
    if not source:
        raise HTTPException(status_code=404, detail=f"Raster artifact '{artifact}' is not available.")
    try:
        return sample_raster(source, latitude=latitude, longitude=longitude, artifact=artifact)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analysis/{result_id}/preview/image")
def preview_analysis_raster_image(
    result_id: str,
    artifact: str = Query(..., pattern="^(water_depth_raster|flood_mask_raster|velocity_raster|arrival_time_raster|water_level_raster)$"),
    db: Session = Depends(get_db),
):
    record = _result(db, result_id)
    source = record.artifacts.get(_ALLOWED[artifact])
    if not source:
        raise HTTPException(status_code=404, detail=f"Raster artifact '{artifact}' is not available.")
    output = _root() / record.id / "previews" / f"{artifact}.png"
    if not output.exists():
        try:
            build_raster_preview(source, output, mask=artifact == "flood_mask_raster", artifact=artifact)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(output, media_type="image/png", filename=output.name)


@router.get("/analysis/{result_id}/package")
def export_analysis_package(result_id: str, db: Session = Depends(get_db)):
    record = _result(db, result_id)
    try:
        path, media_type = build_analysis_package(record, _root() / record.id)
    except ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/comparisons/{comparison_id}")
def export_comparison(comparison_id: str, format: str = Query(..., pattern="^(json|csv)$"), db: Session = Depends(get_db)):
    record = _comparison(db, comparison_id)
    root = _root() / "comparisons" / record.id
    root.mkdir(parents=True, exist_ok=True)
    if format == "json":
        path = root / f"hydroshield_{record.id[:8]}_comparison.json"
        path.write_text(
            __import__('json').dumps({
                "id": record.id,
                "project_id": record.project_id,
                "left_analysis_id": record.left_analysis_id,
                "right_analysis_id": record.right_analysis_id,
                "comparison_type": record.comparison_type,
                "metrics": record.metrics,
                "artifacts": record.artifacts,
                "warnings": record.warnings,
                "assumptions": record.assumptions,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }, indent=2, sort_keys=True),
            encoding='utf-8',
        )
        return FileResponse(path, media_type="application/json", filename=path.name)
    path = root / f"hydroshield_{record.id[:8]}_comparison.csv"
    import csv
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['section', 'key', 'value'])
        for section, data in [('metrics', record.metrics), ('warnings', {str(i): v for i, v in enumerate(record.warnings)}), ('assumptions', record.assumptions)]:
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value = __import__('json').dumps(value, sort_keys=True)
                writer.writerow([section, key, value])
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=path.name)
