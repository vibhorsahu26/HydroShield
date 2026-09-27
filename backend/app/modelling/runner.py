from __future__ import annotations

import os
import subprocess
import signal
import time
from pathlib import Path
from typing import Any, Callable

from app.core.errors import InternalError
from app.modelling.base import ExecutionResult, ModelAdapter, PreparedModel


class CommandRunner:
    """Run native model steps with timeout, progress and cooperative cancellation."""

    def run(
        self,
        prepared: PreparedModel,
        *,
        adapter: ModelAdapter,
        timeout_s: float,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ExecutionResult:
        workdir = prepared.working_directory
        workdir.mkdir(parents=True, exist_ok=True)
        stdout_log = workdir / "stdout.log"
        stderr_log = workdir / "stderr.log"
        steps = prepared.execution_steps or [prepared.command]
        started = time.perf_counter()
        warnings = list(prepared.warnings)
        step_results: list[dict[str, Any]] = []
        status = "completed"
        exit_code = 0
        aggregate_stdout: list[str] = []
        aggregate_stderr: list[str] = []

        for index, command in enumerate(steps, start=1):
            if cancel_check and cancel_check():
                status, exit_code = "cancelled", -2
                aggregate_stderr.append(f"Step {index} not started: cancellation requested.")
                break

            if progress_callback:
                progress_callback(
                    15.0 + ((index - 1) / max(len(steps), 1)) * 70.0,
                    f"step_{index}_running",
                )

            step_stdout = workdir / f"{index:02d}.stdout.log"
            step_stderr = workdir / f"{index:02d}.stderr.log"
            step_started = time.perf_counter()
            process: subprocess.Popen[bytes] | None = None
            try:
                # IMPORTANT: native solvers such as DualSPHysics can emit a large
                # amount of stdout/stderr. Keeping PIPEs open while calling poll()
                # without draining them can fill the OS pipe buffer and deadlock the
                # child (observed as `anon_pipe_write`). Redirect directly to files
                # instead, and read the completed files after process termination.
                with step_stdout.open("w", encoding="utf-8") as stdout_handle, step_stderr.open(
                    "w", encoding="utf-8"
                ) as stderr_handle:
                    process = subprocess.Popen(
                        command,
                        cwd=workdir,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        text=True,
                        shell=False,
                        env=os.environ.copy(),
                    )
                    while process.poll() is None:
                        if cancel_check and cancel_check():
                            process.terminate()
                            try:
                                process.wait(timeout=2.0)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5.0)
                            stderr_handle.write("\nProcess cancelled.")
                            status, exit_code = "cancelled", -2
                            break

                        if time.perf_counter() - started >= timeout_s:
                            process.terminate()
                            try:
                                process.wait(timeout=2.0)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5.0)
                            stderr_handle.write("\nProcess exceeded timeout.")
                            status, exit_code = "timed_out", -1
                            break
                        time.sleep(0.05)

                    if status not in {"cancelled", "timed_out"}:
                        returncode = process.returncode if process.returncode is not None else -1
                        if returncode < 0:
                            try:
                                signal_name = signal.Signals(-returncode).name
                            except ValueError:
                                signal_name = f"SIG{-returncode}"
                            stderr_handle.write(
                                f"\nProcess terminated by signal {-returncode} ({signal_name})."
                            )
                        step_status = "completed" if returncode == 0 else "failed"
                        status = step_status if returncode != 0 else status
                        exit_code = returncode
                    else:
                        returncode = exit_code

                # File handles are closed/flushed here, so reads see the complete
                # native process output even for long-running jobs.
                out = step_stdout.read_text(encoding="utf-8", errors="replace")
                err = step_stderr.read_text(encoding="utf-8", errors="replace")
                aggregate_stdout.append(f"[STEP {index}]\n{out}")
                aggregate_stderr.append(f"[STEP {index}]\n{err}")
                step_results.append(
                    {
                        "index": index,
                        "status": (
                            "cancelled"
                            if status == "cancelled"
                            else "timed_out"
                            if status == "timed_out"
                            else ("completed" if exit_code == 0 else "failed")
                        ),
                        "exit_code": exit_code,
                        "duration_s": time.perf_counter() - step_started,
                        "command": command,
                    }
                )
                if status in {"cancelled", "timed_out"} or exit_code != 0:
                    break
            except OSError as exc:
                step_stdout.write_text("", encoding="utf-8")
                step_stderr.write_text(str(exc), encoding="utf-8")
                aggregate_stderr.append(f"[STEP {index}]\n{exc}")
                raise InternalError(
                    f"Unable to start {adapter.model.value} model command (step {index}): {exc}"
                ) from exc
        stdout_log.write_text("\n".join(aggregate_stdout), encoding="utf-8")
        stderr_log.write_text("\n".join(aggregate_stderr), encoding="utf-8")
        duration_s = time.perf_counter() - started

        summary, artifacts, parse_warnings = adapter.parse_result(workdir)
        warnings.extend(parse_warnings)
        if status == "failed":
            warnings.append("Model pipeline stopped after a step exited with a non-zero status code.")
        elif status == "timed_out":
            warnings.append("Model pipeline exceeded the configured global timeout budget.")
        elif status == "cancelled":
            warnings.append("Model pipeline was cancelled by the user.")

        if progress_callback:
            progress_callback(100.0 if status == "completed" else 95.0, "execution_finished")

        return ExecutionResult(
            model=adapter.model,
            status=status,
            exit_code=exit_code,
            duration_s=duration_s,
            working_directory=workdir,
            command=prepared.command,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            artifacts=artifacts,
            summary=summary,
            warnings=warnings,
            step_results=step_results,
        )
