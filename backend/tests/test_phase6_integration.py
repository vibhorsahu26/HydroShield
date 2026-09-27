from __future__ import annotations

import io
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from app.geospatial.preprocessing import preprocess_geospatial
from app.modelling.sph.adapter import DualSPHysicsAdapter
from app.modelling.schemas import SphExecutionDevice
from app.schemas.geospatial import GeospatialPreprocessConfig
from app.schemas.scenarios import ScenarioConfig, SimulationModel
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioPreset
from app.scenarios.generator import generate_scenario_variants


def make_dem() -> bytes:
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    profile = {
        "driver": "GTiff",
        "width": 10,
        "height": 10,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(77.0, 28.1, 0.001, 0.001),
        "nodata": -9999.0,
    }
    buf = io.BytesIO()
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(data, 1)
    return buf.getvalue()


def make_river() -> bytes:
    gdf = gpd.GeoDataFrame(
        {"name": ["Integrated River"]},
        geometry=[LineString([(77.002, 28.095), (77.008, 28.095)])],
        crs="EPSG:4326",
    )
    return gdf.to_json().encode()


def case_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<case>
  <casedef>
    <constantsdef><gravity x=\"0\" y=\"0\" z=\"-9.81\" /></constantsdef>
    <geometry><definition dp=\"0.05\" /></geometry>
  </casedef>
  <metadata>
    <duration>{HYDROSHIELD_TIME_MAX_S}</duration>
    <breach>{HYDROSHIELD_BREACH_WIDTH_M}</breach>
  </metadata>
</case>
"""


def _fake_tool(path: Path, body: str) -> list[str]:
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_phase2_to_phase4_to_phase5_to_phase6_chain(tmp_path):
    preprocessed = preprocess_geospatial(
        make_dem(),
        "dem.tif",
        make_river(),
        "river.geojson",
        GeospatialPreprocessConfig(resolution_m=30, river_buffer_m=300),
        tmp_path / "processed",
    )
    base = ScenarioConfig(
        name="Integrated Base",
        initial_reservoir_water_level_m=120,
        reservoir_volume_m3=5_000_000,
        breach_width_m=40,
        breach_depth_m=20,
        breach_formation_time_s=300,
        initial_discharge_m3s=200,
        simulation_duration_s=3600,
        model=SimulationModel.SPH,
    )
    variant = generate_scenario_variants(
        base,
        ScenarioGenerationConfig(presets=[ScenarioPreset.MAJOR_BREACH]),
    )[0]

    native = tmp_path / "native"
    native.mkdir()
    (native / "Case_Def.xml").write_text(case_xml(), encoding="utf-8")

    gencase = _fake_tool(tmp_path / "gencase.py", """import sys
from pathlib import Path
prefix = Path(sys.argv[2])
prefix.parent.mkdir(parents=True, exist_ok=True)
prefix.with_suffix('.xml').write_text('<case/>', encoding='utf-8')
prefix.with_suffix('.bi4').write_bytes(b'case')
""")
    solver = _fake_tool(tmp_path / "solver.py", """import sys
from pathlib import Path
out = Path(sys.argv[3])
(out / 'data').mkdir(parents=True, exist_ok=True)
(out / 'data' / 'Part_0000.bi4').write_bytes(b'frame')
""")
    partvtk = _fake_tool(tmp_path / "partvtk.py", """import sys
from pathlib import Path
args = sys.argv[1:]
prefix = Path(args[args.index('-savecsv') + 1])
prefix.parent.mkdir(parents=True, exist_ok=True)
(prefix.parent / 'PartFluid_0000.csv').write_text('x,y,z,vx,vy,vz\\n0,0,0,3,4,0\\n', encoding='utf-8')
""")

    adapter = DualSPHysicsAdapter(
        device=SphExecutionDevice.CPU,
        gencase_executable=gencase,
        solver_cpu_executable=solver,
        partvtk_executable=partvtk,
    )
    prepared = adapter.prepare(
        variant_parameters=variant.parameters,
        native_input_directory=native,
        working_directory=tmp_path / "model",
        preprocessing_artifacts={
            "dem": preprocessed.dem.path,
            "river": preprocessed.river.path,
            "computational_domain": preprocessed.domain.path,
            "domain_mask": preprocessed.domain.mask_raster_path,
        },
    )
    result = adapter.execute(prepared, timeout_s=30)

    assert result.status == "completed"
    assert result.exit_code == 0
    assert len(result.step_results) == 3
    assert result.summary["max_velocity_mps"] == 5.0
    assert result.summary["particle_count"] == 1
    assert prepared.manifest_path.exists()

    manifest_text = prepared.manifest_path.read_text(encoding="utf-8")
    assert str(preprocessed.dem.path) in manifest_text
    assert '"breach_width_m": 20.0' in manifest_text
