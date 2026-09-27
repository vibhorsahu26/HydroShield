from __future__ import annotations

from pathlib import Path
import json

import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Project, Scenario, ScenarioVariant, SimulationJob
from app.schemas.analysis import ComparisonType, ResultAnalysisRequest, ResultComparisonRequest
from app.services.analysis_service import AnalysisService


def write_depth(path, value, shape=(3, 3), origin=(0, 30)):
    data = np.full(shape, value, dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", width=shape[1], height=shape[0], count=1,
                       dtype="float32", crs="EPSG:32643", transform=from_origin(*origin, 10, 10), nodata=-9999) as dst:
        dst.write(data, 1)


def setup(db):
    project = Project(name="Service Project")
    db.add(project); db.commit(); db.refresh(project)
    scenario = Scenario(project_id=project.id, name="Scenario A", model="both", config={})
    db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="major", kind="breach", preset="major_breach", model="both", parameters={}, assumptions={})
    db.add(variant); db.commit(); db.refresh(variant)
    return project, scenario, variant


def make_job(db, project, scenario, variant, model):
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model=model,
                        status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1,
                        timeout_s=10, config={}, cancel_requested=False, result={})
    db.add(job); db.commit(); db.refresh(job)
    return job


def test_analysis_service_links_result_to_phase7_job(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'service.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    job = make_job(db, project, scenario, variant, "sph")
    depth = tmp_path / "depth.tif"; write_depth(depth, 1.0)

    result = AnalysisService().analyze_job(
        db, job.id,
        ResultAnalysisRequest(water_depth_raster=str(depth), flood_threshold_m=0.05),
    )
    db.refresh(job)
    assert result.simulation_job_id == job.id
    assert job.result["analysis_result_id"] == result.id
    assert result.assumptions["source_inputs"]["water_depth_raster"] == str(depth.resolve())
    db.close(); engine.dispose()


def test_model_and_scenario_comparison_contracts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'compare.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    sph_job = make_job(db, project, scenario, variant, "sph")
    delft_job = make_job(db, project, scenario, variant, "delft3d")
    left_depth = tmp_path / "left.tif"; right_depth = tmp_path / "right.tif"
    write_depth(left_depth, 1.0); write_depth(right_depth, 2.0)
    service = AnalysisService()
    left = service.analyze_job(db, sph_job.id, ResultAnalysisRequest(water_depth_raster=str(left_depth)))
    right = service.analyze_job(db, delft_job.id, ResultAnalysisRequest(water_depth_raster=str(right_depth)))
    comparison = service.compare(db, ResultComparisonRequest(left_analysis_id=left.id, right_analysis_id=right.id, comparison_type=ComparisonType.MODEL))
    assert comparison.comparison_type == "model"
    assert comparison.metrics["depth"]["rmse"] == 1.0
    db.close(); engine.dispose()


def test_invalid_model_and_scenario_comparisons_are_rejected(tmp_path):
    from app.core.errors import ConflictError
    engine = create_engine(f"sqlite:///{tmp_path / 'rules.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    same_model_job_a = make_job(db, project, scenario, variant, "sph")
    same_model_job_b = make_job(db, project, scenario, variant, "sph")
    depth_a = tmp_path / "a.tif"; depth_b = tmp_path / "b.tif"; write_depth(depth_a, 1.0); write_depth(depth_b, 2.0)
    service = AnalysisService()
    left = service.analyze_job(db, same_model_job_a.id, ResultAnalysisRequest(water_depth_raster=str(depth_a)))
    right = service.analyze_job(db, same_model_job_b.id, ResultAnalysisRequest(water_depth_raster=str(depth_b)))
    try:
        service.compare(db, ResultComparisonRequest(left_analysis_id=left.id, right_analysis_id=right.id, comparison_type=ComparisonType.MODEL))
    except ConflictError as exc:
        assert "different model" in exc.message
    else:
        raise AssertionError("Same-model runs must not pass model-comparison validation")
    db.close(); engine.dispose()


def test_native_sph_analysis_bridge_generates_and_persists_outputs(tmp_path):
    from app.database.models import SimulationJob
    from datetime import datetime, timezone

    engine = create_engine(f"sqlite:///{tmp_path / 'native-service.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)

    dem = tmp_path / "dem.tif"
    write_depth(dem, 100.0, shape=(3, 3), origin=(0, 30))
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"
    particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("x;y;z;vx;vy;vz\n5;25;101;0;2;0\n", encoding="utf-8")

    job = SimulationJob(
        project_id=project.id,
        scenario_id=scenario.id,
        variant_id=variant.id,
        model="sph",
        status="completed",
        progress=100,
        current_step="complete",
        attempt=1,
        max_attempts=1,
        timeout_s=10,
        config={"preprocessed_dem": str(dem), "sph_output_interval_s": 1.0},
        working_directory=str(work),
        cancel_requested=False,
        result={},
        finished_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = AnalysisService().analyze_native_sph_job(db, job.id, flood_threshold_m=0.05)
    db.refresh(job)
    assert result.analysis_version == "phase8-native-sph-v1"
    assert result.metrics["max_water_depth_m"] == 1.0
    assert result.metrics["max_velocity_mps"] == 2.0
    assert result.metrics["inundated_area_m2"] == 100.0
    assert result.metrics["inundated_area_km2"] == 0.0001
    assert job.result["analysis_result_id"] == result.id
    assert Path(result.artifacts["water_depth_raster"]).exists()
    assert Path(result.artifacts["flood_extent_geojson"]).exists()

    same = AnalysisService().analyze_native_sph_job(db, job.id, flood_threshold_m=0.05)
    assert same.id == result.id
    db.close(); engine.dispose()


def test_native_delft3d_analysis_bridge_generates_and_persists_outputs(tmp_path):
    from datetime import datetime, timezone
    import xarray as xr

    engine = create_engine(f"sqlite:///{tmp_path / 'native-delft.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)

    dem = tmp_path / "dem.tif"
    write_depth(dem, 100.0, shape=(3, 3), origin=(0, 30))
    work = tmp_path / "work"
    work.mkdir()
    nc = xr.Dataset(
        {"mesh2d_waterdepth": (("time", "nmesh2d_face"), np.array([[0.0, 0.2], [0.7, 0.5]], dtype=float)),
         "mesh2d_ucx": (("time", "nmesh2d_face"), np.array([[0.0, 3.0], [4.0, 0.0]], dtype=float)),
         "mesh2d_ucy": (("time", "nmesh2d_face"), np.array([[0.0, 4.0], [3.0, 5.0]], dtype=float))},
        coords={"time": [0.0, 60.0], "nmesh2d_face": [0, 1],
                "mesh2d_face_x": ("nmesh2d_face", [5.0, 15.0]),
                "mesh2d_face_y": ("nmesh2d_face", [25.0, 15.0])},
        attrs={"epsg": 32643},
    )
    nc.to_netcdf(work / "hydroshield_map.nc", engine="scipy")

    job = SimulationJob(
        project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="delft3d",
        status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1,
        timeout_s=10, config={"preprocessed_dem": str(dem)}, working_directory=str(work),
        cancel_requested=False, result={}, finished_at=datetime.now(timezone.utc),
    )
    db.add(job); db.commit(); db.refresh(job)

    result = AnalysisService().analyze_native_job(db, job.id, flood_threshold_m=0.05)
    db.refresh(job)
    assert result.analysis_version == "phase8-native-delft3d-v1"
    assert result.metrics["max_water_depth_m"] == pytest.approx(0.7, abs=1e-6)
    assert result.metrics["max_velocity_mps"] == pytest.approx(5.0)
    assert result.metrics["inundated_area_m2"] == 200.0
    assert job.result["analysis_result_id"] == result.id
    assert Path(result.artifacts["flood_extent_geojson"]).exists()
    assert result.assumptions["source"] == "native_delft3d_result"
    db.close(); engine.dispose()


def test_scenario_comparison_requires_different_variants(tmp_path):
    from app.core.errors import ConflictError
    engine = create_engine(f"sqlite:///{tmp_path / 'scenario-compare.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    variant2 = ScenarioVariant(base_scenario_id=scenario.id, code="extreme", kind="breach", preset="extreme_breach", model="sph", parameters={}, assumptions={})
    db.add(variant2); db.commit(); db.refresh(variant2)
    job1 = make_job(db, project, scenario, variant, "sph")
    job2 = make_job(db, project, scenario, variant2, "sph")
    depth1 = tmp_path / "a.tif"; depth2 = tmp_path / "b.tif"; write_depth(depth1, 1.0); write_depth(depth2, 2.0)
    service = AnalysisService()
    left = service.analyze_job(db, job1.id, ResultAnalysisRequest(water_depth_raster=str(depth1)))
    right = service.analyze_job(db, job2.id, ResultAnalysisRequest(water_depth_raster=str(depth2)))
    comparison = service.compare(db, ResultComparisonRequest(left_analysis_id=left.id, right_analysis_id=right.id, comparison_type=ComparisonType.SCENARIO))
    assert comparison.comparison_type == "scenario"
    # Same-variant scenario comparison is rejected separately.
    same_job = make_job(db, project, scenario, variant, "sph")
    same = service.analyze_job(db, same_job.id, ResultAnalysisRequest(water_depth_raster=str(depth2)))
    with pytest.raises(ConflictError, match="different scenario variants"):
        service.compare(db, ResultComparisonRequest(left_analysis_id=left.id, right_analysis_id=same.id, comparison_type=ComparisonType.SCENARIO))
    db.close(); engine.dispose()


def test_native_analysis_recovers_dem_from_model_manifest_for_legacy_job(tmp_path):
    from datetime import datetime, timezone
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-manifest.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    dem = tmp_path / "dem.tif"; write_depth(dem, 100.0, shape=(3, 3), origin=(0, 30))
    work = tmp_path / "work"; particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"; particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("x;y;z;vx;vy;vz\n5;25;101;0;1;0\n", encoding="utf-8")
    manifest = work / "hydroshield_model_manifest.json"
    manifest.write_text(json.dumps({"preprocessing_artifacts": {"dem": str(dem)}}), encoding="utf-8")
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={"sph_output_interval_s": 1.0}, working_directory=str(work), manifest_path=str(manifest), cancel_requested=False, result={}, finished_at=datetime.now(timezone.utc))
    db.add(job); db.commit(); db.refresh(job)
    result = AnalysisService().analyze_native_sph_job(db, job.id)
    assert result.metrics["max_water_depth_m"] == 1.0
    db.close(); engine.dispose()


def test_native_analysis_retry_recovers_failed_postprocessing_without_rerunning_solver(tmp_path):
    from datetime import datetime, timezone
    engine = create_engine(f"sqlite:///{tmp_path / 'retry-native.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project, scenario, variant = setup(db)
    dem = tmp_path / "dem.tif"
    write_depth(dem, 100.0, shape=(2, 2), origin=(0, 20))
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"
    particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("x;y;z;vx;vy;vz\n5;15;101;0;3;0\n", encoding="utf-8")
    job = SimulationJob(
        project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph",
        status="failed", progress=99, current_step="result_processing_failed", attempt=1, max_attempts=1,
        timeout_s=10, config={"preprocessed_dem": str(dem), "sph_output_interval_s": 1.0},
        working_directory=str(work), cancel_requested=False,
        result={"postprocessing": {"status": "failed", "error": "old parser failure"}},
        error_message="old parser failure", finished_at=datetime.now(timezone.utc),
    )
    db.add(job); db.commit(); db.refresh(job)

    result = AnalysisService().analyze_native_job(db, job.id, flood_threshold_m=0.05, force=True)
    db.refresh(job)
    assert result.metrics["max_water_depth_m"] == 1.0
    assert job.status == "completed"
    assert job.current_step == "complete"
    assert job.progress == 100.0
    assert job.error_message is None
    assert job.result["postprocessing"]["status"] == "completed"
    db.close(); engine.dispose()
