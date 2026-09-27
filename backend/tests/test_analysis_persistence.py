from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import AnalysisResult, Project, Scenario, ScenarioVariant, SimulationJob
from app.database.repositories.analysis import AnalysisResultRepository, ResultComparisonRepository


def test_analysis_and_comparison_persist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Analysis Project")
    scenario = Scenario(project_id=project.id if project.id else None, name="S", model="sph", config={})
    db.add(project); db.commit(); db.refresh(project)
    scenario.project_id = project.id
    db.add(scenario); db.commit(); db.refresh(scenario)
    variant = ScenarioVariant(base_scenario_id=scenario.id, code="major", kind="breach", preset="major_breach", model="sph", parameters={}, assumptions={})
    db.add(variant); db.commit(); db.refresh(variant)
    job = SimulationJob(project_id=project.id, scenario_id=scenario.id, variant_id=variant.id, model="sph", status="completed", progress=100, current_step="complete", attempt=1, max_attempts=1, timeout_s=10, config={}, cancel_requested=False)
    db.add(job); db.commit(); db.refresh(job)

    result = AnalysisResultRepository().create(
        db, simulation_job_id=job.id, project_id=project.id, scenario_id=scenario.id, variant_id=variant.id,
        analysis_version="phase8-v1", flood_threshold_m=0.05,
        metrics={"inundated_area_m2": 10}, exposure={"layers": {}}, artifacts={"water_depth_raster":"depth.tif", "flood_mask_raster":"mask.tif", "flood_extent_geojson":"extent.geojson"},
        warnings=[], assumptions={"method":"test"},
    )
    comparison = ResultComparisonRepository().create(
        db, project_id=project.id, left_analysis_id=result.id, right_analysis_id=result.id,
        comparison_type="model", metrics={}, artifacts={}, warnings=[], assumptions={}
    )
    assert AnalysisResultRepository().get(db, result.id).metrics["inundated_area_m2"] == 10
    assert ResultComparisonRepository().get(db, comparison.id).project_id == project.id
    db.close(); engine.dispose()
