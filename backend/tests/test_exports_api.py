from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.database.base import Base
from app.database.models import AnalysisResult
from app.database.session import get_db
from app.main import create_app


def _setup_result(db: Session, tmp_path: Path) -> str:
    import rasterio
    from rasterio.transform import from_origin

    result_id = "result-export"
    project_id = "project-export"
    scenario_id = "scenario-export"
    variant_id = "variant-export"
    job_id = "job-export"
    flood = tmp_path / "flood.geojson"
    gpd.GeoDataFrame({"flooded": [1]}, geometry=[Polygon([(0, 30), (20, 30), (20, 10), (0, 10)])], crs="EPSG:32643").to_file(flood, driver="GeoJSON")
    depth = tmp_path / "depth.tif"
    mask = tmp_path / "mask.tif"
    velocity = tmp_path / "velocity.tif"
    arrival = tmp_path / "arrival.tif"
    level = tmp_path / "level.tif"
    profile = {"driver":"GTiff","width":2,"height":2,"count":1,"dtype":"float32","crs":"EPSG:32643","transform":from_origin(0,30,10,10),"nodata":-9999}
    for path, values in [(depth, [[0.0,1.0],[2.0,0.5]]),(mask, [[0,1],[1,1]]),(velocity, [[0.0,1.0],[2.0,3.0]]),(arrival, [[0,9],[8,7]]),(level, [[100,101],[102,100.5]])]:
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(np.array(values, dtype="float32"), 1)
    record = AnalysisResult(
        id=result_id,
        simulation_job_id=job_id,
        project_id=project_id,
        scenario_id=scenario_id,
        variant_id=variant_id,
        analysis_version="phase8-v1",
        flood_threshold_m=0.05,
        metrics={"max_water_depth_m": 2.0},
        exposure={"exposed_area_m2": 300.0, "layers": {}},
        artifacts={"water_depth_raster": str(depth), "flood_mask_raster": str(mask), "velocity_raster": str(velocity), "arrival_time_raster": str(arrival), "water_level_raster": str(level), "flood_extent_geojson": str(flood)},
        warnings=[],
        assumptions={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    return result_id


@pytest.fixture()
def export_client(tmp_path, monkeypatch):
    db_path = tmp_path / "export_api.db"
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("HYDROSHIELD_EXPORT_ROOT", str(tmp_path / "api_exports"))
    from app.core.config import get_settings
    get_settings.cache_clear()
    db = SessionLocal()
    result_id = _setup_result(db, tmp_path)
    db.close()
    try:
        yield TestClient(app), result_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_analysis_export_api(export_client):
    client, result_id = export_client
    response = client.get(f"/api/v1/exports/analysis/{result_id}", params={"format": "geojson"})
    assert response.status_code == 200
    assert "flooded" in response.text

    response = client.get(f"/api/v1/exports/analysis/{result_id}", params={"format": "geotiff", "artifact": "water_depth"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/tiff")

    response = client.get(f"/api/v1/exports/analysis/{result_id}/package")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert any(name.endswith(".geojson") for name in archive.namelist())
        assert any(name.endswith(".json") for name in archive.namelist())


def test_flood_zones_api_returns_depth_polygons(export_client):
    client, result_id = export_client
    response = client.get(f"/api/v1/exports/analysis/{result_id}/flood-zones")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]
    properties = payload["features"][0]["properties"]
    assert {"zone", "depth_min_m", "depth_max_m", "area_km2", "cell_count", "color"}.issubset(properties)
    assert payload["bbox"] and len(payload["bbox"]) == 2


def test_comparison_export_api(export_client):
    from datetime import datetime, timezone
    from app.database.models import ResultComparison

    client, result_id = export_client
    override = client.app.dependency_overrides[get_db]
    generator = override()
    db = next(generator)
    comparison = ResultComparison(
        project_id="project-export",
        left_analysis_id=result_id,
        right_analysis_id=result_id,
        comparison_type="scenario",
        metrics={"flood":{"jaccard":0.75},"depth":{"mae":0.12}},
        artifacts={},
        warnings=[],
        assumptions={"difference_definition":"right_minus_left"},
        created_at=datetime.now(timezone.utc),
    )
    db.add(comparison); db.commit(); db.refresh(comparison)
    comparison_id = comparison.id
    generator.close()

    for fmt in ("json", "csv"):
        response = client.get(f"/api/v1/exports/comparisons/{comparison_id}", params={"format": fmt})
        assert response.status_code == 200
        assert response.content
        if fmt == "json":
            assert response.headers["content-type"].startswith("application/json")
            assert b"scenario" in response.content
        else:
            assert response.headers["content-type"].startswith("text/csv")
            assert b"difference_definition" in response.content
