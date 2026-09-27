from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import shutil
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.modelling.auto_case import generate_dualsphysics_case
from app.modelling.runtime import SolverRuntimeDetector
from app.modelling.schemas import SphExecutionDevice
from app.modelling.sph.adapter import DualSPHysicsAdapter
from app.schemas.scenarios import SimulationModel
from app.core.config import Settings


def main() -> int:
    if os.getenv("HYDROSHIELD_REAL_SOLVER_SMOKE") != "1":
        print("SKIP: set HYDROSHIELD_REAL_SOLVER_SMOKE=1 to launch a real DualSPHysics smoke simulation")
        return 0
    settings = Settings(environment="development", database_url="sqlite:///./real_smoke.db")
    runtime = SolverRuntimeDetector(settings).detect()["sph"]
    if not runtime.ready:
        raise SystemExit("DualSPHysics runtime is unavailable; build with auto-provisioning first.")
    device = SphExecutionDevice.CPU
    with tempfile.TemporaryDirectory(prefix="hydroshield-sph-smoke-") as td:
        root = Path(td)
        dem = root / "dem.tif"
        with rasterio.open(
            dem, "w", driver="GTiff", height=3, width=3, count=1, dtype="float32",
            crs="EPSG:32643", transform=from_origin(500_000, 3_000_000, 10, 10)
        ) as dst:
            dst.write(np.zeros((3, 3), dtype=np.float32), 1)
        variant = {
            "release_mode": "dam_breach", "model": SimulationModel.SPH.value,
            "initial_reservoir_water_level_m": 2.0, "reservoir_volume_m3": 1000.0,
            "breach_width_m": 10.0, "breach_depth_m": 1.0,
            "breach_formation_time_s": 0.1, "initial_discharge_m3s": 1.0,
            "controlled_release_discharge_m3s": None, "simulation_duration_s": 0.5,
        }
        native = root / "native"
        generate_dualsphysics_case(variant_parameters=variant, dem_path=dem, output_dir=native)
        adapter = DualSPHysicsAdapter(bin_dir=settings.dual_sph_bin_dir, device=device)
        prepared = adapter.prepare(variant_parameters=variant, native_input_directory=native, working_directory=root / "run", preprocessing_artifacts={"dem": str(dem)})
        result = adapter.execute(prepared, timeout_s=120)
        if result.status != "completed":
            raise SystemExit(f"DualSPHysics smoke run failed: {result.status} exit={result.exit_code} warnings={result.warnings}")
        print(f"DualSPHysics smoke run completed in {result.duration_s:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
