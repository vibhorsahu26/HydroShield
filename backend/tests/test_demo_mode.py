import json
from pathlib import Path

from app.analysis.result_processor import process_result
from app.modelling.demo import generate_demo_case
from app.modelling.runtime import SolverRuntimeDetector
from app.core.config import Settings
import numpy as np


def test_demo_case_produces_normal_analysis_artifacts(tmp_path: Path):
    generated = generate_demo_case(tmp_path)
    result = process_result(
        water_depth_raster=generated["water_depth_raster"],
        velocity_raster=generated["velocity_raster"],
        arrival_time_raster=generated["arrival_time_raster"],
        water_level_raster=generated["water_level_raster"],
        dem_raster=generated["dem_raster"],
        discharge_csv=generated["discharge_csv"],
        flood_threshold_m=0.05,
        output_dir=tmp_path / "analysis",
        exposure_layers={},
    )
    assert result["metrics"]["inundated_area_m2"] > 0
    assert result["metrics"]["max_water_depth_m"] > 0
    assert result["metrics"]["max_velocity_mps"] > 0
    assert result["metrics"]["first_arrival_time_s"] > 0
    assert result["metrics"]["max_water_level_m"] > 0
    assert result["metrics"]["max_discharge_m3s"] > 0
    for key in ("water_depth_raster", "flood_mask_raster", "flood_extent_geojson", "velocity_raster", "arrival_time_raster", "water_level_raster"):
        assert Path(result["artifacts"][key]).is_file()


def test_demo_mode_reports_sph_ready_without_native_binaries():
    settings = Settings(demo_mode=True)
    runtime = SolverRuntimeDetector(settings).detect_dualsphysics()
    assert runtime.ready is True
    assert runtime.available is True
    assert runtime.version == "5.4.3"
    assert runtime.effective_device == "cpu"
    assert runtime.warnings == []


def test_demo_case_changes_with_scenario_variant_inputs(tmp_path):
    partial = generate_demo_case(tmp_path / "partial", variant_parameters={"release_mode":"dam_breach","initial_discharge_m3s":62.5,"breach_width_m":12.5,"breach_depth_m":2.5,"simulation_duration_s":3600.0})
    extreme = generate_demo_case(tmp_path / "extreme", variant_parameters={"release_mode":"dam_breach","initial_discharge_m3s":250.0,"breach_width_m":50.0,"breach_depth_m":10.0,"simulation_duration_s":3600.0})
    assert partial["summary"]["variant_scale"] < extreme["summary"]["variant_scale"]
    assert partial["summary"]["max_water_depth_m"] < extreme["summary"]["max_water_depth_m"]


def test_demo_case_uses_prepared_dem_and_river_geometry(tmp_path: Path):
    import json
    from shapely.geometry import LineString, mapping
    import rasterio
    from rasterio.transform import from_origin

    dem_path = tmp_path / "prepared_dem.tif"
    data = np.linspace(100, 130, 900, dtype="float32").reshape(30, 30)
    with rasterio.open(
        dem_path, "w", driver="GTiff", height=30, width=30, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(77.0, 29.0, 0.001, 0.001), nodata=-9999.0
    ) as dst:
        dst.write(data, 1)
    river_path = tmp_path / "river.geojson"
    river_path.write_text(json.dumps({
        "type":"FeatureCollection",
        "features":[{"type":"Feature","properties":{"name":"Live River"},"geometry":mapping(LineString([(77.005,28.995),(77.010,28.990),(77.015,28.985)]))}]
    }), encoding="utf-8")

    generated = generate_demo_case(
        tmp_path / "run",
        variant_parameters={"release_mode":"dam_breach","initial_discharge_m3s":150.0,"breach_width_m":30.0,"breach_depth_m":6.0,"simulation_duration_s":3600.0},
        dem_raster=dem_path,
        river_vector=river_path,
        run_signature="run-1",
    )
    with rasterio.open(generated["dem_raster"]) as src:
        assert src.crs.to_string() == "EPSG:4326"
        assert src.width <= 480 and src.height <= 480
    assert 0 < generated["summary"]["max_water_depth_m"] <= 8.0
    assert 0 < generated["summary"]["max_velocity_mps"] <= 5.5
    assert generated["summary"]["first_arrival_time_s"] > 0


def test_demo_case_repeated_runs_have_small_spatial_variation(tmp_path: Path):
    a = generate_demo_case(tmp_path / "a", variant_parameters={"release_mode":"dam_breach","initial_discharge_m3s":200.0,"breach_width_m":40.0,"breach_depth_m":8.0,"simulation_duration_s":3600.0}, run_signature="job-a")
    b = generate_demo_case(tmp_path / "b", variant_parameters={"release_mode":"dam_breach","initial_discharge_m3s":200.0,"breach_width_m":40.0,"breach_depth_m":8.0,"simulation_duration_s":3600.0}, run_signature="job-b")
    assert a["summary"]["max_water_depth_m"] != b["summary"]["max_water_depth_m"]


def test_demo_case_scenario_outputs_are_distinct_and_bounded(tmp_path):
    from app.schemas.scenarios import ScenarioConfig, SimulationModel
    from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
    from app.scenarios.generator import generate_scenario_variants

    base = ScenarioConfig(
        name="Scenario output check",
        initial_reservoir_water_level_m=120,
        reservoir_volume_m3=5_000_000,
        breach_width_m=50,
        breach_depth_m=20,
        breach_formation_time_s=1800,
        initial_discharge_m3s=0,
        simulation_duration_s=3600,
        model=SimulationModel.SPH,
    )
    variants = generate_scenario_variants(
        base,
        ScenarioGenerationConfig(presets=list(ScenarioPreset), controlled_release_discharge_m3s=75),
    )
    summaries = []
    for variant in variants:
        generated = generate_demo_case(tmp_path / variant.code, variant_parameters=variant.parameters, run_signature=variant.code)
        summaries.append(generated["summary"])
    depths = [round(item["max_water_depth_m"], 3) for item in summaries]
    areas = []
    for variant in variants:
        result = process_result(
            water_depth_raster=str(tmp_path / variant.code / "analysis_engine" / "water_depth_raster.tif"),
            velocity_raster=str(tmp_path / variant.code / "analysis_engine" / "velocity_raster.tif"),
            arrival_time_raster=str(tmp_path / variant.code / "analysis_engine" / "arrival_time_raster.tif"),
            water_level_raster=str(tmp_path / variant.code / "analysis_engine" / "water_level_raster.tif"),
            dem_raster=str(tmp_path / variant.code / "analysis_engine" / "study_dem.tif"),
            discharge_csv=str(tmp_path / variant.code / "analysis_engine" / "discharge.csv"),
            flood_threshold_m=0.05,
            output_dir=tmp_path / variant.code / "analysis",
            exposure_layers={},
        )
        areas.append(round(result["metrics"]["inundated_area_m2"], 1))
    assert len(set(depths)) >= 3
    assert len(set(areas)) >= 3
    assert all(0 < item["max_water_depth_m"] <= 8.0 for item in summaries)
    assert all(0 < item["max_velocity_mps"] <= 5.5 for item in summaries)
    assert all(item["max_water_level_m"] < 200 for item in summaries)


def test_demo_case_delft3d_is_model_specific_and_differs_from_sph(tmp_path: Path):
    params = {
        "release_mode": "dam_breach",
        "initial_discharge_m3s": 180.0,
        "breach_width_m": 35.0,
        "breach_depth_m": 7.0,
        "simulation_duration_s": 3600.0,
    }
    sph = generate_demo_case(tmp_path / "sph", variant_parameters=params, run_signature="same", model="sph")
    delft = generate_demo_case(tmp_path / "delft3d", variant_parameters=params, run_signature="same", model="delft3d")
    assert json.loads(Path(sph["manifest_path"]).read_text())['model'] == 'sph'
    assert json.loads(Path(delft["manifest_path"]).read_text())['model'] == 'delft3d'
    assert sph["summary"]["max_water_depth_m"] != delft["summary"]["max_water_depth_m"]


def test_development_queues_delft3d_fallback_when_runtime_missing(tmp_path, monkeypatch):
    from app.modelling.runtime import SolverRuntime
    from app.orchestration.manager import SimulationJobManager
    from app.schemas.scenarios import SimulationModel
    from app.database.repositories.simulation_jobs import SimulationJobRepository
    from tests.test_orchestration import setup_db, wait_for_status

    monkeypatch.setenv("HYDROSHIELD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "false")
    from app.core.config import get_settings
    get_settings.cache_clear()

    engine, SessionLocal, project_id, scenario_id, variant_id = setup_db(tmp_path)
    db = SessionLocal()
    try:
        variant = db.get(__import__("app.database.models", fromlist=["ScenarioVariant"]).ScenarioVariant, variant_id)
        variant.model = "both"
        db.commit()
    finally:
        db.close()

    manager = SimulationJobManager(session_factory=SessionLocal, max_workers=1)
    real = manager.modelling
    real.runtime_status = lambda: {
        "sph": SolverRuntime("sph", False, False, None, "gpu", None, None, {"gencase": None, "gpu": None, "cpu": None, "partvtk": None}, {"available": False, "count": 0, "devices": [], "source": None}, ["unavailable"]),
        "delft3d": SolverRuntime("delft3d", False, False, None, None, None, None, {"dimr": None, "dflowfm": None, "runner": None}, {"available": False, "count": 0, "devices": [], "source": None}, ["unavailable"]),
    }
    db = SessionLocal()
    try:
        job = manager.create_and_submit(
            db,
            project_id=project_id,
            scenario_id=scenario_id,
            variant_id=variant_id,
            model=SimulationModel.DELFT3D,
            prepare=__import__("app.modelling.schemas", fromlist=["ModelPrepareRequest"]).ModelPrepareRequest(timeout_s=10),
            max_attempts=1,
        )
    finally:
        db.close()
    done = wait_for_status(SessionLocal, job.id, timeout=10)
    assert done.status == "completed", done.error_message
    assert done.result["summary"]["max_water_depth_m"] > 0
    manager.shutdown(wait=True)
    engine.dispose()


def test_delft3d_api_queues_when_runtime_missing_in_development(tmp_path, monkeypatch):
    from app.modelling.runtime import SolverRuntime
    from app.modelling.schemas import ModelPrepareRequest
    from app.schemas.scenarios import SimulationModel
    from tests.test_orchestration import valid_base
    from tests.test_simulation_jobs_api import make_client, wait_terminal

    monkeypatch.setenv("HYDROSHIELD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "false")
    from app.core.config import get_settings
    get_settings.cache_clear()

    client, engine, manager = make_client(tmp_path)
    manager.modelling.runtime_status = lambda: {
        "sph": SolverRuntime("sph", False, False, None, "gpu", None, None, {"gencase": None, "gpu": None, "cpu": None, "partvtk": None}, {"available": False, "count": 0, "devices": [], "source": None}, ["unavailable"]),
        "delft3d": SolverRuntime("delft3d", False, False, None, None, None, None, {"dimr": None, "dflowfm": None, "runner": None}, {"available": False, "count": 0, "devices": [], "source": None}, ["unavailable"]),
    }
    native = tmp_path / "native"
    native.mkdir()
    try:
        project = client.post("/api/v1/projects", json={"name": "Delft fallback API"}).json()
        scenario_payload = valid_base().model_dump(mode="json")
        scenario_payload["model"] = "both"
        scenario = client.post(f"/api/v1/projects/{project['id']}/scenarios", json=scenario_payload)
        assert scenario.status_code == 201, scenario.text
        scenario_id = scenario.json()["id"]
        generated = client.post(f"/api/v1/projects/{project['id']}/scenarios/{scenario_id}/variants/generate", json={"presets": ["major_breach"]})
        assert generated.status_code == 201, generated.text
        variants = client.get(f"/api/v1/projects/{project['id']}/scenarios/{scenario_id}/variants")
        assert variants.status_code == 200, variants.text
        variant_id = variants.json()[0]["id"]

        response = client.post("/api/v1/simulations", json={
            "project_id": project["id"],
            "scenario_id": scenario_id,
            "variant_id": variant_id,
            "model": "delft3d",
            "prepare": ModelPrepareRequest(native_input_directory=str(native), timeout_s=10).model_dump(mode="json"),
            "max_attempts": 1,
        })
        assert response.status_code == 202, response.text
        final = wait_terminal(client, response.json()["id"])
        assert final["status"] == "completed", final
        assert final["result"]["summary"]["max_water_depth_m"] > 0
    finally:
        manager.shutdown(wait=True)
        client.close()
        engine.dispose()
