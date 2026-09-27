from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
import pytest
import xarray as xr

from app.modelling.delft3d.adapter import Delft3DAdapter
from app.modelling.delft3d.parser import parse_results as parse_delft_results
from app.modelling.schemas import Delft3DRunnerMode, SphExecutionDevice
from app.modelling.sph.adapter import DualSPHysicsAdapter, SPHAdapter
from app.schemas.scenarios import SimulationModel


BASE_VARIANT = {
    "release_mode": "dam_breach",
    "model": "sph",
    "initial_reservoir_water_level_m": 120.0,
    "reservoir_volume_m3": 5_000_000.0,
    "breach_width_m": 20.0,
    "breach_depth_m": 10.0,
    "breach_formation_time_s": 100.0,
    "initial_discharge_m3s": 100.0,
    "controlled_release_discharge_m3s": None,
    "simulation_duration_s": 200.0,
}


def _case_xml(with_bathy: bool = False) -> str:
    bathy = (
        "<drawbathymetry><zpoints file=\"{HYDROSHIELD_BATHYMETRY_FILE}\" />"
        "<grid dp=\"5\" /></drawbathymetry>"
        if with_bathy
        else ""
    )
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<case>
  <casedef>
    <constantsdef>
      <gravity x=\"0\" y=\"0\" z=\"-9.81\" />
    </constantsdef>
    <geometry>
      <definition dp=\"0.05\" pointmin=\"0\" />
      {bathy}
    </geometry>
  </casedef>
  <metadata>
    <simulation_duration>{'{HYDROSHIELD_TIME_MAX_S}'}</simulation_duration>
    <output_interval>{'{HYDROSHIELD_TIME_OUT_S}'}</output_interval>
    <breach_width>{'{HYDROSHIELD_BREACH_WIDTH_M}'}</breach_width>
    <breach_depth>{'{HYDROSHIELD_BREACH_DEPTH_M}'}</breach_depth>
    <breach_time>{'{HYDROSHIELD_BREACH_FORMATION_TIME_S}'}</breach_time>
    <discharge>{'{HYDROSHIELD_INITIAL_DISCHARGE_M3S}'}</discharge>
    <reservoir_level>{'{HYDROSHIELD_RESERVOIR_WATER_LEVEL_M}'}</reservoir_level>
    <reservoir_volume>{'{HYDROSHIELD_RESERVOIR_VOLUME_M3}'}</reservoir_volume>
  </metadata>
</case>
"""


def test_delft3d_dflowfm_command_uses_official_autostartstop_shape(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    (native / "model.mdu").write_text("[model]\n", encoding="utf-8")
    prepared = Delft3DAdapter(runner_mode=Delft3DRunnerMode.DFLOWFM, executable="dflowfm").prepare(
        variant_parameters={"release_mode": "dam_breach"},
        native_input_directory=native,
        working_directory=tmp_path / "work",
    )
    assert prepared.command == ["dflowfm", "--autostartstop", str(native / "model.mdu")]
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["model"] == "delft3d"
    assert manifest["variant_parameters"]["release_mode"] == "dam_breach"


def test_delft3d_requires_native_input_for_selected_runner(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    with pytest.raises(ValueError, match="DIMR configuration"):
        Delft3DAdapter(runner_mode=Delft3DRunnerMode.DIMR, executable="run_dimr.sh").prepare(
            variant_parameters={}, native_input_directory=native, working_directory=tmp_path / "work"
        )


def test_delft3d_parser_extracts_canonical_metrics(tmp_path):
    times = np.array([0.0, 10.0, 20.0])
    depth = np.array([[0.0, 0.0], [0.1, 0.0], [0.3, 0.2]])
    ux = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    uy = np.array([[0.0, 0.0], [0.0, 2.0], [0.0, 3.0]])
    ds = xr.Dataset(
        data_vars={
            "mesh2d_waterdepth": (("time", "nmesh2d_face"), depth),
            "mesh2d_ucx": (("time", "nmesh2d_face"), ux),
            "mesh2d_ucy": (("time", "nmesh2d_face"), uy),
            "mesh2d_flowelem_ba": (("nmesh2d_face",), np.array([10.0, 20.0])),
        },
        coords={"time": times},
    )
    out = tmp_path / "run_map.nc"
    ds.to_netcdf(out, engine="scipy")
    summary, artifacts, warnings = parse_delft_results(tmp_path)
    assert not warnings
    assert summary["max_water_depth_m"] == pytest.approx(0.3)
    assert summary["max_velocity_mps"] == pytest.approx(3.0)
    assert summary["inundated_area_m2"] == pytest.approx(30.0)
    assert summary["first_arrival_time_s"] == pytest.approx(10.0)
    assert summary["wet_cell_count"] == 3
    assert out in artifacts


def _write_fake_tool(path: Path, body: str) -> list[str]:
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_dualsphysics_prepares_official_three_step_pipeline(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    (native / "Case_Def.xml").write_text(_case_xml(), encoding="utf-8")
    adapter = DualSPHysicsAdapter(
        device=SphExecutionDevice.GPU,
        gpu_id=2,
        gencase_executable=["gencase"],
        solver_gpu_executable=["dualsphysics"],
        partvtk_executable=["partvtk"],
        output_interval_s=2.5,
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT,
        native_input_directory=native,
        working_directory=tmp_path / "work",
    )
    assert prepared.adapter_version.startswith("2.7-dualsphysics")
    assert prepared.command[:2] == ["gencase", "Case_Def"]
    assert len(prepared.execution_steps) == 3
    assert prepared.execution_steps[1][0] == "dualsphysics"
    assert "-gpu:2" in prepared.execution_steps[1]
    assert "-cellmode:H" not in prepared.execution_steps[1]
    assert "-tmax:200.0" in prepared.execution_steps[1]
    assert "-tout:2.5" in prepared.execution_steps[1]
    assert prepared.execution_steps[2][0] == "partvtk"
    rendered = (prepared.working_directory / "Case_Def.xml").read_text(encoding="utf-8")
    assert "{HYDROSHIELD_" not in rendered
    assert "<breach_width>20</breach_width>" in rendered
    payload = json.loads((prepared.working_directory / "sph_input.json").read_text(encoding="utf-8"))
    assert payload["engine_version"] == "5.4.3"
    assert payload["commands"]["solver"][1] == "-gpu:2"


def test_dualsphysics_automatic_case_uses_runtime_safe_gencase_options(tmp_path):
    from app.modelling.auto_case import generate_dualsphysics_case
    dem = tmp_path / "processed_dem.tif"
    with rasterio.open(
        dem, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
        crs="EPSG:32643", transform=from_origin(500_000, 3_000_000, 10, 10)
    ) as dst:
        dst.write(np.array([[10.0, 11.0], [12.0, 13.0]], dtype=np.float32), 1)
    native = tmp_path / "native"
    generate_dualsphysics_case(variant_parameters=BASE_VARIANT, dem_path=dem, output_dir=native)
    adapter = DualSPHysicsAdapter(
        gencase_executable=["gencase"], solver_gpu_executable=["dualsphysics"], partvtk_executable=["partvtk"]
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT, native_input_directory=native,
        working_directory=tmp_path / "work", preprocessing_artifacts={"dem": str(dem)}
    )
    assert "-save:bi" in prepared.execution_steps[0]
    assert "-ompthreads:2" in prepared.execution_steps[0]
    assert "-save:all" not in prepared.execution_steps[0]
    # `-cellmode` belongs to the DualSPHysics solver, never to GenCase.
    assert "-cellmode:H" not in prepared.execution_steps[0]
    assert "-cellmode:H" in prepared.execution_steps[1]
    assert "-cellmode:2" not in prepared.execution_steps[1]


def test_dualsphysics_automatic_solver_uses_named_cellmode_cli_value(tmp_path):
    from app.modelling.auto_case import generate_dualsphysics_case
    dem = tmp_path / "processed_dem.tif"
    with rasterio.open(
        dem, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
        crs="EPSG:32643", transform=from_origin(500_000, 3_000_000, 10, 10)
    ) as dst:
        dst.write(np.array([[10.0, 11.0], [12.0, 13.0]], dtype=np.float32), 1)
    native = tmp_path / "native"
    generate_dualsphysics_case(variant_parameters=BASE_VARIANT, dem_path=dem, output_dir=native)
    adapter = DualSPHysicsAdapter(
        gencase_executable=["gencase"], solver_gpu_executable=["dualsphysics"], partvtk_executable=["partvtk"]
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT, native_input_directory=native,
        working_directory=tmp_path / "work", preprocessing_artifacts={"dem": str(dem)}
    )
    gencase = prepared.execution_steps[0]
    solver = prepared.execution_steps[1]
    # DualSPHysics v5.4 CLI uses named aliases: H/HALF or 2H/FULL.
    assert "-cellmode:2" not in gencase
    assert "-cellmode:2" not in solver
    assert "-cellmode:H" in solver


def test_dualsphysics_stages_auto_generated_bathymetry_into_execution_directory(tmp_path):
    from app.modelling.auto_case import generate_dualsphysics_case
    import rasterio
    from rasterio.transform import from_origin

    dem = tmp_path / 'processed_dem.tif'
    with rasterio.open(
        dem, 'w', driver='GTiff', height=2, width=2, count=1, dtype='float32',
        crs='EPSG:32643', transform=from_origin(500_000, 3_000_000, 10, 10)
    ) as dst:
        dst.write(np.array([[10.0, 11.0], [12.0, 13.0]], dtype=np.float32), 1)

    native = tmp_path / 'native'
    generate_dualsphysics_case(variant_parameters=BASE_VARIANT, dem_path=dem, output_dir=native)
    adapter = DualSPHysicsAdapter(
        gencase_executable=['gencase'],
        solver_gpu_executable=['dualsphysics'],
        partvtk_executable=['partvtk'],
    )

    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT,
        native_input_directory=native,
        working_directory=tmp_path / 'work',
        preprocessing_artifacts={'dem': str(dem)},
    )

    staged = prepared.working_directory / 'HydroShield_Bathymetry.csv'
    assert staged.exists()
    assert staged.read_text(encoding='utf-8') == (native / 'HydroShield_Bathymetry.csv').read_text(encoding='utf-8')
    rendered = (prepared.working_directory / 'Case_Def.xml').read_text(encoding='utf-8')
    assert 'HydroShield_Bathymetry.csv' in rendered
    assert 'drawfilecsv' in rendered
    assert "-cellmode:H" in prepared.execution_steps[1]
    assert "-cellmode:2" not in prepared.execution_steps[1]


def test_dualsphysics_rejects_zpoints_reference_outside_native_directory(tmp_path):
    native = tmp_path / 'native'
    native.mkdir()
    (tmp_path / 'outside.xyz').write_text('0 0 0\n', encoding='utf-8')
    (native / 'Case_Def.xml').write_text(
        '<case><casedef><geometry><commands><mainlist>'
        '<drawbathymetry><zpoints file="../outside.xyz"/></drawbathymetry>'
        '</mainlist></commands></geometry></casedef></case>',
        encoding='utf-8',
    )
    adapter = DualSPHysicsAdapter(
        gencase_executable=['gencase'], solver_gpu_executable=['dualsphysics'], partvtk_executable=['partvtk']
    )
    with pytest.raises(ValueError, match='escapes the native input directory'):
        adapter.prepare(
            variant_parameters=BASE_VARIANT,
            native_input_directory=native,
            working_directory=tmp_path / 'work',
        )


def test_dualsphysics_converts_phase4_dem_to_bathymetry_xyz(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    native = tmp_path / "native"
    native.mkdir()
    (native / "Case_Def.xml").write_text(_case_xml(with_bathy=True), encoding="utf-8")
    dem = tmp_path / "processed_dem.tif"
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    with rasterio.open(
        dem,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(500_000, 3_000_000, 10, 10),
    ) as dst:
        dst.write(data, 1)
    adapter = DualSPHysicsAdapter(
        gencase_executable=["gencase"],
        solver_gpu_executable=["dualsphysics"],
        partvtk_executable=["partvtk"],
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT,
        native_input_directory=native,
        working_directory=tmp_path / "work",
        preprocessing_artifacts={"dem": str(dem)},
    )
    xyz = prepared.working_directory / "HydroShield_Bathymetry.xyz"
    assert xyz.exists()
    assert len(xyz.read_text(encoding="utf-8").strip().splitlines()) == 4
    rendered = (prepared.working_directory / "Case_Def.xml").read_text(encoding="utf-8")
    assert "{HYDROSHIELD_BATHYMETRY_FILE}" not in rendered
    assert "HydroShield_Bathymetry.xyz" in rendered


def test_dualsphysics_fake_toolchain_executes_and_parses_particle_csv(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    (native / "Case_Def.xml").write_text(_case_xml(), encoding="utf-8")

    gencase = _write_fake_tool(
        tmp_path / "fake_gencase.py",
        """import sys
from pathlib import Path
prefix = Path(sys.argv[2])
prefix.parent.mkdir(parents=True, exist_ok=True)
prefix.with_suffix('.xml').write_text('<case/>', encoding='utf-8')
Path(str(prefix) + '.bi4').write_bytes(b'case')
""",
    )
    solver = _write_fake_tool(
        tmp_path / "fake_solver.py",
        """import sys
from pathlib import Path
out = Path(sys.argv[3])
(out / 'data').mkdir(parents=True, exist_ok=True)
(out / 'Run.out').write_text('synthetic DualSPHysics run', encoding='utf-8')
(out / 'data' / 'Part_0000.bi4').write_bytes(b'frame0')
(out / 'data' / 'Part_0001.bi4').write_bytes(b'frame1')
""",
    )
    partvtk = _write_fake_tool(
        tmp_path / "fake_partvtk.py",
        """import sys
from pathlib import Path
args = sys.argv[1:]
dirdata = Path(args[args.index('-dirdata') + 1])
prefix = Path(args[args.index('-savecsv') + 1])
prefix.parent.mkdir(parents=True, exist_ok=True)
header = 'x,y,z,vx,vy,vz\\n'
(prefix.parent / (prefix.name + '_0000.csv')).write_text(header + '0,0,0,1,0,0\\n', encoding='utf-8')
(prefix.parent / (prefix.name + '_0001.csv')).write_text(header + '1,0,0,0,3,4\\n2,0,0,0,0,5\\n', encoding='utf-8')
""",
    )

    adapter = DualSPHysicsAdapter(
        device=SphExecutionDevice.CPU,
        gencase_executable=gencase,
        solver_cpu_executable=solver,
        partvtk_executable=partvtk,
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT,
        native_input_directory=native,
        working_directory=tmp_path / "work",
    )
    result = adapter.execute(prepared, timeout_s=30)
    assert result.status == "completed"
    assert result.exit_code == 0
    assert len(result.step_results) == 3
    assert result.summary["time_steps"] == 2
    assert result.summary["particle_count"] == 2
    assert result.summary["max_velocity_mps"] == pytest.approx(5.0)
    assert (prepared.working_directory / "stdout.log").exists()
    assert (prepared.working_directory / "01.stdout.log").exists()
    assert (prepared.working_directory / "dual_sphysics" / "HydroShieldCase_out" / "particles" / "PartFluid_0001.csv").exists()


def test_dualsphysics_stops_pipeline_on_solver_failure(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    (native / "Case_Def.xml").write_text(_case_xml(), encoding="utf-8")
    gencase = _write_fake_tool(tmp_path / "fake_gencase.py", "from pathlib import Path; import sys; Path(sys.argv[2] + '.xml').parent.mkdir(parents=True, exist_ok=True); Path(sys.argv[2] + '.xml').write_text('<case/>')")
    solver = _write_fake_tool(tmp_path / "fake_solver.py", "import sys; sys.exit(9)")
    partvtk = _write_fake_tool(tmp_path / "fake_partvtk.py", "from pathlib import Path; Path('should_not_exist').write_text('bad')")
    adapter = DualSPHysicsAdapter(
        gencase_executable=gencase,
        solver_gpu_executable=solver,
        partvtk_executable=partvtk,
    )
    prepared = adapter.prepare(
        variant_parameters=BASE_VARIANT,
        native_input_directory=native,
        working_directory=tmp_path / "work",
    )
    result = adapter.execute(prepared, timeout_s=30)
    assert result.status == "failed"
    assert result.exit_code == 9
    assert len(result.step_results) == 2
    assert not (tmp_path / "work" / "should_not_exist").exists()
    assert any("non-zero" in warning for warning in result.warnings)


# Historical name remains supported as a stable alias.
def test_sph_adapter_alias_points_to_dualsphysics():
    assert SPHAdapter is DualSPHysicsAdapter


def test_delft3d_dimr_command_uses_config_file(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    (native / "dimr_config.xml").write_text("<dimrConfigVersion>1.2</dimrConfigVersion>", encoding="utf-8")
    prepared = Delft3DAdapter(runner_mode=Delft3DRunnerMode.DIMR, executable="run_dimr.sh").prepare(
        variant_parameters={"release_mode": "dam_breach"},
        native_input_directory=native,
        working_directory=tmp_path / "work",
        preprocessing_artifacts={"dem": "/data/dem.tif"},
    )
    assert prepared.command == ["run_dimr.sh", str(native / "dimr_config.xml")]
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["preprocessing_artifacts"]["dem"] == "/data/dem.tif"


def test_dualsphysics_default_binaries_match_v54_toolchain():
    from app.modelling.sph.input_builder import _DEFAULT_BINARIES
    assert _DEFAULT_BINARIES["Linux"]["gencase"] == "GenCase_linux64"
    assert _DEFAULT_BINARIES["Linux"]["gpu"] == "DualSPHysics5.4_linux64"
    assert _DEFAULT_BINARIES["Linux"]["cpu"] == "DualSPHysics5.4CPU_linux64"
    assert _DEFAULT_BINARIES["Linux"]["partvtk"] == "PartVTK_linux64"


def test_sph_parser_ignores_statistics_csv_without_particle_coordinates(tmp_path):
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"
    particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text(
        "TimeStep;Np;Nbound;Nfixed;Nmoving;Nfloat;Nfluid\n0;10;5;5;0;0;5\n",
        encoding="utf-8",
    )
    from app.modelling.sph.parser import parse_results
    summary, artifacts, warnings = parse_results(work)
    assert summary is None
    assert any("none are particle tables" in warning for warning in warnings)
    assert any("TimeStep" in warning for warning in warnings)
