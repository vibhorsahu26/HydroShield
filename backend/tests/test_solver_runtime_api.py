from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_solver_preflight_endpoint(monkeypatch, tmp_path):
    original = get_settings()
    from app.api.routes import solver_runtime
    from app.modelling.runtime import SolverRuntime

    fake = {
        "sph": SolverRuntime("sph", True, True, "5.4.3", "gpu", "cpu", None, {"gencase": "/g", "gpu": "/gpu", "cpu": "/cpu", "partvtk": "/p"}, {"available": False, "count": 0, "devices": [], "source": None}, ["CPU fallback"]),
        "delft3d": SolverRuntime("delft3d", False, False, None, None, None, None, {"dimr": None, "dflowfm": None, "runner": None}, {"available": False, "count": 0, "devices": [], "source": None}, ["Unavailable"]),
    }
    monkeypatch.setattr(solver_runtime.SolverRuntimeDetector, "detect", lambda self: fake)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/modelling/preflight")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sph"]["ready"] is True
    assert payload["sph"]["effective_device"] == "cpu"
    assert payload["delft3d"]["ready"] is False
