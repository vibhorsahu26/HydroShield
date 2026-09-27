from fastapi import APIRouter

from app.api.routes import (
    analysis_inputs,
    acquisition,
    dataset_uploads,
    dataset_previews,
    datasets,
    exports,
    geospatial,
    health,
    modelling,
    model_inputs,
    projects,
    results,
    scenarios,
    simulations,
    satellite,
    solver_runtime,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(scenarios.router)
api_router.include_router(datasets.router)
api_router.include_router(geospatial.router)
api_router.include_router(projects.router)
api_router.include_router(dataset_uploads.router)
api_router.include_router(dataset_previews.router)
api_router.include_router(model_inputs.router)
api_router.include_router(modelling.router)
api_router.include_router(simulations.router)
api_router.include_router(results.router)
api_router.include_router(analysis_inputs.router)
api_router.include_router(acquisition.router)
api_router.include_router(satellite.router)
api_router.include_router(solver_runtime.router)
api_router.include_router(exports.router)
