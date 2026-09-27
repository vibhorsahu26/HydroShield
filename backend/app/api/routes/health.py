from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


def _ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".hydroshield-ready"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


@router.get("/health/ready")
def readiness(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    for name, path in {
        "processing_storage": settings.processing_work_dir,
        "upload_storage": settings.storage_root,
        "export_storage": settings.export_root,
        "model_storage": settings.model_work_dir,
    }.items():
        try:
            _ensure_writable_directory(path)
            checks[name] = "ok"
        except Exception:
            checks[name] = "error"

    if settings.database_url.startswith("postgres"):
        try:
            version = db.execute(text("SELECT PostGIS_Version()")).scalar_one()
            checks["postgis"] = "ok" if version else "error"
        except Exception:
            checks["postgis"] = "error"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
