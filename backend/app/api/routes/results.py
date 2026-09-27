from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from pathlib import Path

from app.database.session import get_db
from app.database.models import SimulationJob, ScenarioVariant
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.modelling.schemas import ModelPrepareRequest
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
from app.schemas.scenarios import SimulationModel
from app.api.routes.simulations import get_job_manager
from app.core.config import get_settings
from app.schemas.analysis import AnalysisResultResponse, DemoComparisonRequest, DemoComparisonResponse, NativeResultProcessRequest, ResultAnalysisRequest, ResultComparisonRequest, ResultComparisonResponse
from app.services.analysis_service import AnalysisService
from app.core.errors import ConflictError, NotFoundError
from app.exports.preview import build_raster_preview

router = APIRouter(prefix="/results", tags=["results"])
service = AnalysisService()


@router.post("/simulations/{job_id}/analyze", response_model=AnalysisResultResponse, status_code=201)
def analyze_simulation(job_id: str, payload: ResultAnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResultResponse:
    return service.analyze_job(db, job_id, payload)

@router.post("/simulations/{job_id}/process-native", response_model=AnalysisResultResponse, status_code=201)
def process_native_result(job_id: str, payload: NativeResultProcessRequest, db: Session = Depends(get_db)) -> AnalysisResultResponse:
    try:
        return service.analyze_native_job(
            db,
            job_id,
            flood_threshold_m=payload.flood_threshold_m,
            force=payload.force,
        )
    except (ConflictError, NotFoundError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Native result processing failed: {exc}") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Native result files could not be read or written: {exc}") from exc


@router.get("/simulations/{job_id}/timeline")
def simulation_timeline(job_id: str, db: Session = Depends(get_db), max_frames: int = Query(default=24, ge=1, le=60)):
    """Return browser-safe water-depth frames for supported prototype/native jobs.

    The endpoint only serves files declared by the persisted job result and requires
    them to live under the configured model-work directory.
    """
    from app.database.models import SimulationJob

    job = db.get(SimulationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Simulation job not found.")
    result = job.result or {}
    result_artifacts = result.get("artifacts")
    artifacts = result.get("timeline")
    if artifacts is None and isinstance(result_artifacts, dict):
        artifacts = result_artifacts.get("time_series_water_depth")
    if artifacts is None and isinstance(result_artifacts, list):
        artifacts = [item for item in result_artifacts if isinstance(item, str) and "water_depth_t" in Path(item).name]
    if not artifacts:
        artifacts = []
    if not artifacts:
        return {"job_id": job_id, "available": False, "frames": []}

    settings = get_settings()
    allowed_roots = [Path(settings.model_work_dir).resolve()]
    if job.working_directory:
        allowed_roots.append(Path(job.working_directory).resolve())
    metadata_by_path = {}
    manifest_path = Path(job.manifest_path) if job.manifest_path else None
    if manifest_path and manifest_path.exists():
        try:
            manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            for item in manifest.get("artifacts", {}).get("time_series_metadata", []):
                if item.get("path"):
                    metadata_by_path[str(Path(item["path"]).resolve())] = item
            if isinstance(artifacts, list) and artifacts and isinstance(artifacts[0], dict):
                artifacts = [item.get("path") for item in artifacts if item.get("path")]
        except Exception:
            pass

    frames = []
    for index, raw_path in enumerate(artifacts[:max_frames]):
        if not raw_path:
            continue
        source = Path(raw_path).resolve()
        if not any(root == source or root in source.parents for root in allowed_roots):
            raise HTTPException(status_code=403, detail="Timeline artifact is outside the configured HydroShield run directory.")
        if not source.is_file():
            continue
        frame = metadata_by_path.get(str(source), {})
        output = Path(settings.export_root) / "timelines" / job_id / f"frame-{index:04d}.png"
        try:
            bounds, metadata = build_raster_preview(source, output, artifact="water_depth_raster")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Timeline frame could not be previewed: {exc}") from exc
        frames.append({
            "index": int(frame.get("index", index)),
            "time_s": float(frame.get("time_s", index * 600.0)),
            "image_path": f"/results/simulations/{job_id}/timeline/image?frame={index}",
            "bounds": bounds,
            "metadata": metadata,
        })
    return {"job_id": job_id, "available": bool(frames), "source": result.get("execution_mode", result.get("status", "unknown")), "frames": frames}


@router.get("/simulations/{job_id}/timeline/image")
def simulation_timeline_image(job_id: str, frame: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    from app.database.models import SimulationJob

    job = db.get(SimulationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Simulation job not found.")
    result = job.result or {}
    result_artifacts = result.get("artifacts")
    artifacts = result.get("timeline")
    if artifacts is None and isinstance(result_artifacts, dict):
        artifacts = result_artifacts.get("time_series_water_depth")
    if artifacts is None and isinstance(result_artifacts, list):
        artifacts = [item for item in result_artifacts if isinstance(item, str) and "water_depth_t" in Path(item).name]
    if artifacts is None:
        artifacts = []
    if isinstance(artifacts, list) and artifacts and isinstance(artifacts[0], dict):
        artifacts = [item.get("path") for item in artifacts]
    if frame >= len(artifacts):
        raise HTTPException(status_code=404, detail="Timeline frame not found.")
    source = Path(artifacts[frame]).resolve()
    settings = get_settings()
    allowed_roots = [Path(settings.model_work_dir).resolve()]
    if job.working_directory:
        allowed_roots.append(Path(job.working_directory).resolve())
    if not any(root == source or root in source.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Timeline artifact is outside the configured HydroShield run directory.")
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Timeline frame file is not available.")
    output = Path(get_settings().export_root) / "timelines" / job_id / f"frame-{frame:04d}.png"
    try:
        build_raster_preview(source, output, artifact="water_depth_raster")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Timeline frame could not be previewed: {exc}") from exc
    return FileResponse(output, media_type="image/png", filename=output.name)


@router.get("/simulations/{job_id}", response_model=list[AnalysisResultResponse])
def list_simulation_results(job_id: str, db: Session = Depends(get_db)) -> list[AnalysisResultResponse]:
    return service.list_for_job(db, job_id)


@router.get("/{result_id}", response_model=AnalysisResultResponse)
def get_result(result_id: str, db: Session = Depends(get_db)) -> AnalysisResultResponse:
    return service.get_result(db, result_id)


@router.post("/compare", response_model=ResultComparisonResponse, status_code=201)
def compare_results(payload: ResultComparisonRequest, db: Session = Depends(get_db)) -> ResultComparisonResponse:
    return service.compare(db, payload)


@router.post("/comparison-demo", response_model=DemoComparisonResponse, status_code=202)
def create_demo_comparison(
    payload: DemoComparisonRequest,
    db: Session = Depends(get_db),
    manager = Depends(get_job_manager),
) -> DemoComparisonResponse:
    """Queue a second SPH scenario variant for prototype comparison workflows."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=409, detail="Prototype comparison mode is disabled.")

    source = service.results.get(db, payload.source_analysis_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source analysis result not found.")
    source_job = source.simulation_job
    if source_job is None or source_job.model != SimulationModel.SPH.value:
        raise HTTPException(status_code=409, detail="Prototype comparison requires a completed SPH analysis.")

    variants_repo = ScenarioVariantRepository()
    existing = variants_repo.list_for_scenario(db, source.scenario_id)
    source_variant = next((item for item in existing if item.id == source.variant_id), None)
    source_code = source_variant.code if source_variant else ""
    preferred = payload.preferred_preset
    fallback_order = [ScenarioPreset.PARTIAL_BREACH.value, ScenarioPreset.MAJOR_BREACH.value, ScenarioPreset.EXTREME_BREACH.value, ScenarioPreset.CONTROLLED_RELEASE.value]
    if preferred and preferred in fallback_order:
        candidates = [preferred, *[item for item in fallback_order if item != preferred]]
    else:
        candidates = fallback_order.copy()
        if source_code in candidates:
            candidates.remove(source_code)
            candidates.append(source_code)

    comparison_variant = next((item for item in existing if item.id != source.variant_id and item.code in candidates), None)
    if comparison_variant is None:
        for preset in candidates:
            if preset == source_code:
                continue
            config = ScenarioGenerationConfig(presets=[ScenarioPreset(preset)])
            try:
                from app.services.scenario_service import ScenarioService
                ScenarioService().generate_variants(db, project_id=source.project_id, scenario_id=source.scenario_id, config=config)
                comparison_variant = next((item for item in variants_repo.list_for_scenario(db, source.scenario_id) if item.code == preset), None)
                if comparison_variant is not None:
                    break
            except Exception:
                # Try the next preset if a previously-created variant caused a conflict.
                continue
    if comparison_variant is None:
        raise HTTPException(status_code=409, detail="No additional prototype scenario variant is available for comparison.")

    existing_jobs = (
        db.query(SimulationJob)
        .filter(
            SimulationJob.project_id == source.project_id,
            SimulationJob.scenario_id == source.scenario_id,
            SimulationJob.variant_id == comparison_variant.id,
            SimulationJob.model == SimulationModel.SPH.value,
        )
        .order_by(SimulationJob.created_at.desc())
        .all()
    )
    existing_job = next((item for item in existing_jobs if item.status in {"queued", "preparing", "running", "processing", "completed"}), None)
    if existing_job is not None:
        return DemoComparisonResponse(
            project_id=source.project_id,
            scenario_id=source.scenario_id,
            source_analysis_id=source.id,
            comparison_variant_id=comparison_variant.id,
            comparison_variant_code=comparison_variant.code,
            comparison_variant_preset=comparison_variant.preset,
            simulation_job_id=existing_job.id,
            model=SimulationModel.SPH.value,
            status=existing_job.status,
            prototype=True,
        )

    config_data = dict(source_job.config or {})
    config_data["working_directory"] = None
    config_data["native_input_directory"] = None
    config_data["auto_generate"] = False
    prepare = ModelPrepareRequest.model_validate(config_data)
    job = manager.create_and_submit(
        db,
        project_id=source.project_id,
        scenario_id=source.scenario_id,
        variant_id=comparison_variant.id,
        model=SimulationModel.SPH,
        prepare=prepare,
        max_attempts=1,
    )
    return DemoComparisonResponse(
        project_id=source.project_id,
        scenario_id=source.scenario_id,
        source_analysis_id=source.id,
        comparison_variant_id=comparison_variant.id,
        comparison_variant_code=comparison_variant.code,
        comparison_variant_preset=comparison_variant.preset,
        simulation_job_id=job.id,
        model=SimulationModel.SPH.value,
        status=job.status,
        prototype=True,
    )


@router.get("/comparisons/{comparison_id}", response_model=ResultComparisonResponse)
def get_comparison(comparison_id: str, db: Session = Depends(get_db)) -> ResultComparisonResponse:
    return service.get_comparison(db, comparison_id)
