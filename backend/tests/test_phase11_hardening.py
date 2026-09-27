from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.middleware import RequestBodyLimitMiddleware
from app.database.base import Base
from app.database.session import build_session_factory
from app.main import create_app


def test_production_settings_require_postgres_and_explicit_hosts():
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            database_url="sqlite:///./prod.db",
            docs_enabled=False,
            allowed_hosts=["api.example.com"],
            allowed_origins=["https://app.example.com"],
        )


def test_production_settings_reject_wildcards_and_docs():
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://u:p@localhost/db",
            docs_enabled=True,
            allowed_hosts=["api.example.com"],
            allowed_origins=["https://app.example.com"],
        )
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://u:p@localhost/db",
            docs_enabled=False,
            allowed_hosts=["*"],
            allowed_origins=["https://app.example.com"],
        )


def test_health_has_request_id_and_security_headers():
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_request_id_is_preserved_when_supplied():
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"X-Request-ID": "release-test-123"})
    assert response.headers["X-Request-ID"] == "release-test-123"


def test_production_app_hides_docs(monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_ENVIRONMENT", "production")
    monkeypatch.setenv("HYDROSHIELD_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("HYDROSHIELD_ALLOWED_HOSTS", '["api.example.com"]')
    monkeypatch.setenv("HYDROSHIELD_ALLOWED_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("HYDROSHIELD_DOCS_ENABLED", "false")
    app = create_app()
    client = TestClient(app)
    headers = {"host": "api.example.com"}
    assert client.get("/docs", headers=headers).status_code == 404
    assert client.get("/openapi.json", headers=headers).status_code == 404


def test_readiness_passes_for_local_sqlite(tmp_path):
    db_path = tmp_path / "ready.db"
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        processing_work_dir=tmp_path / "processed",
        storage_root=tmp_path / "uploads",
        export_root=tmp_path / "exports",
        model_work_dir=tmp_path / "models",
    )
    from app.api.routes.health import readiness

    with session_factory() as db:
        response = readiness(settings=settings, db=db)
    assert response["status"] == "ready"
    assert all(value == "ok" for value in response["checks"].values())
    engine.dispose()


def test_large_content_length_is_rejected_by_middleware():
    app = create_app()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=10)
    client = TestClient(app)
    response = client.post("/api/v1/health", content=b"12345678901", headers={"content-length": "11"})
    assert response.status_code in {405, 413}
    if response.status_code == 413:
        assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_production_files_exist_and_are_nonempty():
    for relative in [
        "Dockerfile",
        ".dockerignore",
        ".env.production.example",
        "docker-compose.production.yml",
        "scripts/start.sh",
        ".github/workflows/ci.yml",
        "docs/production.md",
    ]:
        path = Path(relative)
        assert path.exists() and path.stat().st_size > 0


def test_readiness_reports_not_ready_for_unwritable_path(monkeypatch, tmp_path):
    from app.api.routes.health import readiness
    engine = create_engine(f"sqlite:///{tmp_path / 'ready2.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    SessionLocal = build_session_factory(engine)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ready2.db'}",
        processing_work_dir=tmp_path / "processed",
        storage_root=tmp_path / "uploads",
        export_root=tmp_path / "exports",
        model_work_dir=tmp_path / "models",
    )
    # A path nested beneath a file cannot be created and should fail readiness.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    settings.model_work_dir = blocker / "nested"
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            readiness(settings=settings, db=db)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["checks"]["model_storage"] == "error"
    engine.dispose()


def test_configurable_upload_limit_is_shared_with_validator(tmp_path):
    from app.services.dataset_storage import DatasetStorageService
    from app.schemas.datasets import DatasetType
    service = DatasetStorageService(tmp_path)
    with pytest.raises(ValueError, match="exceeds the 1 MB upload limit"):
        service.validate_and_store(
            "project-id",
            "sample.csv",
            b"x" * (1024 * 1024 + 1),
            DatasetType.RAINFALL,
            max_upload_bytes=1024 * 1024,
        )


def test_docker_runtime_has_single_uvicorn_worker_healthcheck_and_native_raster_dependency():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    start = Path("scripts/start.sh").read_text(encoding="utf-8")
    assert "USER hydroshield" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "apt-get install -y --no-install-recommends libexpat1" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
    assert "--workers 1" in start
    assert "--proxy-headers" in start
    assert "exec uvicorn" in start


def test_compose_requires_explicit_production_security_inputs():
    compose = Path("docker-compose.production.yml").read_text(encoding="utf-8")
    assert "HYDROSHIELD_DATABASE_URL: ${HYDROSHIELD_DATABASE_URL:?Set HYDROSHIELD_DATABASE_URL}" in compose
    assert "HYDROSHIELD_ALLOWED_HOSTS: ${HYDROSHIELD_ALLOWED_HOSTS:?Set HYDROSHIELD_ALLOWED_HOSTS as a JSON list}" in compose
    assert "HYDROSHIELD_ALLOWED_ORIGINS: ${HYDROSHIELD_ALLOWED_ORIGINS:?Set HYDROSHIELD_ALLOWED_ORIGINS as a JSON list}" in compose
    assert "HYDROSHIELD_RUN_MIGRATIONS_ON_STARTUP: \"true\"" in compose


def test_ci_workflow_runs_strict_tests():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m compileall -q app" in workflow
    assert "python -m pytest -q -W error" in workflow


def test_compose_healthcheck_uses_a_configured_allowed_host():
    from pathlib import Path
    root = Path("../docker-compose.yml").read_text(encoding="utf-8")
    prod = Path("docker-compose.production.yml").read_text(encoding="utf-8")
    snippet = "from app.core.config import get_settings; host=get_settings().allowed_hosts[0]"
    assert snippet in root
    assert snippet in prod
    assert "headers={'Host': host}" in root
    assert "headers={'Host': host}" in prod


def test_local_compose_uses_same_origin_without_localhost_cors(monkeypatch):
    from pathlib import Path
    compose = Path("../docker-compose.yml").read_text(encoding="utf-8")
    assert "HYDROSHIELD_ALLOWED_ORIGINS: '[]'" in compose
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://u:p@localhost/db",
        docs_enabled=False,
        allowed_hosts=["localhost", "127.0.0.1"],
        allowed_origins=[],
    )
    assert settings.allowed_origins == []


def test_root_runtime_configuration_exposes_dualsphysics_libs_and_delft3d_path():
    root = Path("../docker-compose.yml").read_text(encoding="utf-8")
    assert "HYDROSHIELD_DELFT3D_BIN_DIR: /opt/delft3d/bin" in root
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "LD_LIBRARY_PATH=/opt/dualsphysics/bin" in dockerfile


def test_run_script_has_gpu_to_cpu_fallback():
    script = Path("../run.ps1").read_text(encoding="utf-8")
    assert "docker-compose.gpu.yml" in script
    assert "CPU mode" in script
    assert "restarting HydroShield in CPU mode" in script


def test_docker_provisions_dualsphysics_and_exports_runtime_path():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    provisioner = Path("scripts/provision_dualsphysics.sh").read_text(encoding="utf-8")
    assert "HYDROSHIELD_AUTO_PROVISION_DUALSPHYSICS=true" in dockerfile
    assert "provision_dualsphysics.sh" in dockerfile
    assert "HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR" in dockerfile and "/opt/dualsphysics/bin" in dockerfile
    assert "LD_LIBRARY_PATH=/opt/dualsphysics/bin" in dockerfile
    assert "DualSPHysics5.4CPU_linux64" in provisioner
    assert "GenCase_linux64" in provisioner
    assert "PartVTK_linux64" in provisioner
