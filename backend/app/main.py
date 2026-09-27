from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import (
    HydroShieldError,
    hydroshield_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestBodyLimitMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.database.session import SessionLocal
from app.orchestration.manager import SimulationJobManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.run_migrations_on_startup:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
    for path in (settings.processing_work_dir, settings.storage_root, settings.export_root, settings.model_work_dir):
        path.mkdir(parents=True, exist_ok=True)
    manager = getattr(app.state, "job_manager", None)
    owns_manager = manager is None
    if manager is None:
        manager = SimulationJobManager(session_factory=SessionLocal, max_workers=settings.job_worker_count)
        app.state.job_manager = manager
    manager.recover_pending()
    reconcile = getattr(manager, "reconcile_completed_native_results", None)
    if callable(reconcile):
        reconcile()
    try:
        yield
    finally:
        if owns_manager:
            manager.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="HydroShield automated dam-break and flood inundation backend.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_exception_handler(HydroShieldError, hydroshield_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.environment.lower() == "production":
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
        if settings.enforce_https:
            app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
