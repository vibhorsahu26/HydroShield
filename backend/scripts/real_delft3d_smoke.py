from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.core.config import Settings
from app.modelling.auto_case import generate_delft3d_case
from app.modelling.runtime import SolverRuntimeDetector
from app.modelling.delft3d.adapter import Delft3DAdapter
from app.modelling.schemas import Delft3DRunnerMode
from app.schemas.scenarios import SimulationModel


def main() -> int:
    if os.getenv("HYDROSHIELD_REAL_DELFT3D_SMOKE") != "1":
        print("SKIP: set HYDROSHIELD_REAL_DELFT3D_SMOKE=1 to launch a real Delft3D FM smoke simulation")
        return 0
    settings = Settings(environment="development", database_url="sqlite:///./real_smoke.db")
    runtime = SolverRuntimeDetector(settings).detect()["delft3d"]
    if not runtime.ready:
        raise SystemExit("Delft3D FM runtime is unavailable; configure HYDROSHIELD_DELFT3D_BIN_DIR or PATH first.")
    mode = Delft3DRunnerMode(runtime.runner_mode or Delft3DRunnerMode.DIMR.value)
    with tempfile.TemporaryDirectory(prefix="hydroshield-delft3d-smoke-") as td:
        root = Path(td)
        dem = root / "dem.tif"
        with rasterio.open(
            dem, "w", driver="GTiff", height=3, width=3, count=1, dtype="float32",
            crs="EPSG:32643", transform=from_origin(500_000, 3_000_000, 10, 10)
        ) as dst:
            dst.write(np.zeros((3, 3), dtype=np.float32), 1)
        variant = {
            "release_mode": "dam_breach", "model": SimulationModel.DELFT3D.value,
            "initial_reservoir_water_level_m": 2.0, "reservoir_volume_m3": 1000.0,
            "breach_width_m": 10.0, "breach_depth_m": 1.0,
            "breach_formation_time_s": 0.1, "initial_discharge_m3s": 1.0,
            "controlled_release_discharge_m3s": None, "simulation_duration_s": 1.0,
        }
        native = root / "native"
        generate_delft3d_case(variant_parameters=variant, dem_path=dem, output_dir=native)
        adapter = Delft3DAdapter(runner_mode=mode, executable=str(runtime.binaries["runner"]))
        prepared = adapter.prepare(variant_parameters=variant, native_input_directory=native, working_directory=root / "run", preprocessing_artifacts={"dem": str(dem)})
        result = adapter.execute(prepared, timeout_s=120)
        if result.status != "completed":
            raise SystemExit(f"Delft3D smoke run failed: {result.status} exit={result.exit_code} warnings={result.warnings}")
        print(f"Delft3D smoke run completed in {result.duration_s:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
