from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.modelling.runtime import SolverRuntimeDetector
from app.schemas.solver_runtime import SolverPreflightResponse, SolverRuntimeStatus, GpuRuntimeStatus

router = APIRouter(prefix="/modelling", tags=["solver-runtime"])


def _serialize(status):
    return SolverRuntimeStatus(
        ready=status.ready,
        available=status.available,
        version=status.version,
        device=status.device,
        effective_device=status.effective_device,
        runner_mode=status.runner_mode,
        binaries=status.binaries,
        gpu=GpuRuntimeStatus.model_validate(status.gpu),
        warnings=status.warnings,
    )


@router.get("/preflight", response_model=SolverPreflightResponse)
def solver_preflight() -> SolverPreflightResponse:
    runtimes = SolverRuntimeDetector(get_settings()).detect()
    return SolverPreflightResponse(
        sph=_serialize(runtimes["sph"]),
        delft3d=_serialize(runtimes["delft3d"]),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
