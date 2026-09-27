from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.modelling.base import ModelAdapter, PreparedModel
from app.modelling.runner import CommandRunner
from app.schemas.scenarios import SimulationModel


class FakeAdapter(ModelAdapter):
    model = SimulationModel.SPH
    adapter_version = "test"

    def prepare(self, *, variant_parameters, native_input_directory, working_directory):
        raise NotImplementedError

    def parse_result(self, working_directory: Path):
        return None, [], []

    def execute(self, prepared, *, timeout_s):
        return CommandRunner().run(prepared, adapter=self, timeout_s=timeout_s)


def prepared(command, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    manifest = work / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    return PreparedModel(
        model=SimulationModel.SPH,
        adapter_version="test",
        working_directory=work,
        manifest_path=manifest,
        command=command,
    )


def test_runner_captures_nonzero_exit(tmp_path):
    result = FakeAdapter().execute(
        prepared([sys.executable, "-c", "import sys; print('bad'); sys.exit(3)"], tmp_path),
        timeout_s=30,
    )
    assert result.status == "failed"
    assert result.exit_code == 3
    assert "bad" in (tmp_path / "work" / "stdout.log").read_text(encoding="utf-8")


def test_runner_enforces_timeout(tmp_path):
    result = FakeAdapter().execute(
        prepared([sys.executable, "-c", "import time; time.sleep(2)"], tmp_path),
        timeout_s=0.1,
    )
    assert result.status == "timed_out"
    assert result.exit_code == -1
    assert "timeout" in (tmp_path / "work" / "stderr.log").read_text(encoding="utf-8").lower()


def test_runner_does_not_deadlock_on_large_native_output(tmp_path):
    code = (
        "import sys; "
        "sys.stdout.write('o' * 300000); sys.stdout.flush(); "
        "sys.stderr.write('e' * 300000); sys.stderr.flush()"
    )
    result = FakeAdapter().execute(
        prepared([sys.executable, "-c", code], tmp_path),
        timeout_s=10,
    )
    assert result.status == "completed"
    assert result.exit_code == 0
    stdout = (tmp_path / "work" / "stdout.log").read_text(encoding="utf-8")
    stderr = (tmp_path / "work" / "stderr.log").read_text(encoding="utf-8")
    assert "o" * 300000 in stdout
    assert "e" * 300000 in stderr
