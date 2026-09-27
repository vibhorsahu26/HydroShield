from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.modelling.runtime import SolverRuntimeDetector
from app.modelling.schemas import SphExecutionDevice


def test_solver_runtime_reports_missing_external_tools(monkeypatch, tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.db'}",
        dual_sph_bin_dir=tmp_path / "missing-dsph",
        delft3d_bin_dir=tmp_path / "missing-delft",
        delft3d_executable="",
    )
    monkeypatch.setattr("app.modelling.runtime.shutil.which", lambda _name: None)
    status = SolverRuntimeDetector(settings).detect()
    assert status["sph"].ready is False
    assert status["sph"].effective_device is None
    assert status["delft3d"].ready is False


def test_dualsphysics_cpu_fallback_when_gpu_not_visible(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("GenCase_linux64", "DualSPHysics5.4_linux64", "DualSPHysics5.4CPU_linux64", "PartVTK_linux64"):
        (bin_dir / name).touch()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.db'}",
        dual_sph_bin_dir=bin_dir,
        dual_sph_device=SphExecutionDevice.GPU.value,
        delft3d_bin_dir=tmp_path / "missing-delft",
        delft3d_executable="",
    )
    monkeypatch.setattr("app.modelling.runtime.SolverRuntimeDetector._detect_gpu", staticmethod(lambda: {"available": False, "count": 0, "devices": [], "source": None}))
    status = SolverRuntimeDetector(settings).detect()["sph"]
    assert status.ready is True
    assert status.effective_device == SphExecutionDevice.CPU.value
    assert any("CPU fallback" in warning for warning in status.warnings)


def test_delft_runtime_prefers_dimr_then_dflowfm(monkeypatch, tmp_path):
    bin_dir = tmp_path / "delft" / "bin"
    bin_dir.mkdir(parents=True)
    dimr = bin_dir / "dimr"
    dflow = bin_dir / "dflowfm"
    dimr.touch(); dflow.touch()
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'runtime.db'}", delft3d_bin_dir=bin_dir, delft3d_executable="")
    status = SolverRuntimeDetector(settings).detect()["delft3d"]
    assert status.ready is True
    assert status.runner_mode == "dimr"
    assert status.binaries["runner"] == str(dimr)

    dimr.unlink()
    status = SolverRuntimeDetector(settings).detect()["delft3d"]
    assert status.ready is True
    assert status.runner_mode == "dflowfm"
    assert status.binaries["runner"] == str(dflow)


def test_delft_runtime_falls_back_to_canonical_command_during_prepare(tmp_path):
    from app.modelling.delft3d.input_builder import build_inputs
    native = tmp_path / "native"
    native.mkdir()
    (native / "dimr_config.xml").write_text("<dimrConfig/>", encoding="utf-8")
    prepared = build_inputs(
        variant_parameters={"release_mode": "dam_breach"},
        native_input_directory=native,
        working_directory=tmp_path / "work",
        runner_mode=__import__("app.modelling.schemas", fromlist=["Delft3DRunnerMode"]).Delft3DRunnerMode.DIMR,
        executable="",
    )
    assert prepared.command[0] == "dimr"


def test_dualsphysics_gpu_runtime_is_ready_when_cpu_binary_is_absent(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("GenCase_linux64", "DualSPHysics5.4_linux64", "PartVTK_linux64"):
        path = bin_dir / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.db'}",
        dual_sph_bin_dir=bin_dir,
        dual_sph_device=SphExecutionDevice.GPU.value,
        delft3d_bin_dir=tmp_path / "missing-delft",
        delft3d_executable="",
    )
    monkeypatch.setattr(
        "app.modelling.runtime.SolverRuntimeDetector._detect_gpu",
        staticmethod(lambda: {"available": True, "count": 1, "devices": [{"index": 0, "name": "NVIDIA Test GPU", "driver_version": "test"}], "source": "test"}),
    )
    status = SolverRuntimeDetector(settings).detect()["sph"]
    assert status.ready is True
    assert status.effective_device == SphExecutionDevice.GPU.value
    assert status.binaries["cpu"] is None


def test_dualsphysics_preflight_distinguishes_installed_gpu_runtime_without_gpu(monkeypatch, tmp_path):
    from pathlib import Path
    from app.modelling.runtime import SolverRuntimeDetector

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ["GenCase_linux64", "DualSPHysics5.4_linux64", "PartVTK_linux64"]:
        p = bin_dir / name
        p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        p.chmod(0o755)

    class Settings:
        dual_sph_bin_dir = Path(bin_dir)
        dual_sph_gencase = None
        dual_sph_solver_gpu = None
        dual_sph_solver_cpu = None
        dual_sph_partvtk = None
        dual_sph_device = "gpu"

    monkeypatch.setattr("app.modelling.runtime.SolverRuntimeDetector._detect_gpu", staticmethod(lambda: {
        "available": False, "count": 0, "devices": [], "source": None
    }))
    status = SolverRuntimeDetector(Settings()).detect_dualsphysics()
    assert status.ready is False
    assert any("GPU is visible inside the container" in w for w in status.warnings)


def test_demo_mode_uses_native_dualsphysics_when_binaries_are_installed(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("GenCase_linux64", "DualSPHysics5.4CPU_linux64", "PartVTK_linux64"):
        path = bin_dir / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.db'}",
        dual_sph_bin_dir=bin_dir,
        dual_sph_device=SphExecutionDevice.GPU.value,
        demo_mode=True,
        delft3d_bin_dir=tmp_path / "missing-delft",
        delft3d_executable="",
    )
    monkeypatch.setattr("app.modelling.runtime.SolverRuntimeDetector._detect_gpu", staticmethod(lambda: {"available": False, "count": 0, "devices": [], "source": None}))
    status = SolverRuntimeDetector(settings).detect_dualsphysics()
    assert status.ready is True
    assert status.effective_device == SphExecutionDevice.CPU.value
    assert status.binaries["gencase"]
    assert status.binaries["cpu"]
    assert status.binaries["partvtk"]
    assert status.warnings
