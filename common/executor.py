"""Submission executor – supports simulated and Docker-based modes.

In **simulated** mode (default) the executor sleeps for randomly drawn
durations that mimic a real compile + judge cycle without requiring Docker.
This isolates the distributed-framework overhead from container overhead and
is the primary mode used for framework benchmarking.

In **docker** mode the executor runs the actual dijudge-sandbox image,
providing a realistic end-to-end measurement.  Requires the Docker socket
to be available inside the benchmark container.
"""
from __future__ import annotations
import os
import random
import time
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common.config import (
    EXECUTION_MODE,
    SANDBOX_IMAGE,
    COMPILE_MIN_MS,
    COMPILE_MAX_MS,
    JUDGE_MIN_MS,
    JUDGE_MAX_MS,
    ARTIFACT_ROOT,
)


@dataclass
class ExecutionResult:
    status: str
    compile_time_ms: Optional[int] = None
    judge_time_ms: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


# ─── Simulated executor ───────────────────────────────────────────────────────

class SimulatedExecutor:
    """Emulates compilation and execution by sleeping.

    Random seeds are derived from submission_id so repeated runs of the
    same submission produce consistent latency distributions.
    """

    def __init__(
        self,
        compile_min_ms: int = COMPILE_MIN_MS,
        compile_max_ms: int = COMPILE_MAX_MS,
        judge_min_ms: int = JUDGE_MIN_MS,
        judge_max_ms: int = JUDGE_MAX_MS,
    ):
        self.compile_min_ms = compile_min_ms
        self.compile_max_ms = compile_max_ms
        self.judge_min_ms = judge_min_ms
        self.judge_max_ms = judge_max_ms

    def _rng(self, submission_id: str, salt: str) -> random.Random:
        return random.Random(hash((submission_id, salt)) & 0xFFFF_FFFF)

    def compile(self, submission_id: str) -> ExecutionResult:
        rng = self._rng(submission_id, "compile")
        t_ms = rng.randint(self.compile_min_ms, self.compile_max_ms)
        time.sleep(t_ms / 1000.0)
        return ExecutionResult(status="compiled", compile_time_ms=t_ms)

    def judge(self, submission_id: str, n_testcases: int) -> ExecutionResult:
        rng = self._rng(submission_id, "judge")
        total_ms = 0
        for _ in range(n_testcases):
            t_ms = rng.randint(self.judge_min_ms, self.judge_max_ms)
            time.sleep(t_ms / 1000.0)
            total_ms += t_ms
        return ExecutionResult(
            status="accepted",
            judge_time_ms=total_ms,
            stdout="Simulated output\n",
        )


# ─── Docker-based executor ────────────────────────────────────────────────────

class DockerExecutor:
    """Wraps the dijudge-sandbox Docker image for real execution.

    Requires the Docker socket to be accessible.  Uses the same nsjail-based
    sandbox as the production system for security parity.
    """

    def __init__(self, sandbox_image: str = SANDBOX_IMAGE, artifact_root: str = ARTIFACT_ROOT):
        import docker  # imported lazily so simulated mode has no docker dep
        self.client = docker.from_env()
        self.sandbox_image = sandbox_image
        self.artifact_root = Path(artifact_root)

    def _artifact_dir(self, submission_id: str) -> Path:
        d = self.artifact_root / submission_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _remove_container(self, container) -> None:
        try:
            container.remove(force=True)
        except Exception:
            pass

    def compile(self, submission_id: str, source_code: str) -> ExecutionResult:
        tmpdir = tempfile.mkdtemp(prefix="exp_cpp_")
        (Path(tmpdir) / "main.cpp").write_text(source_code, encoding="utf-8")
        artifact_dir = self._artifact_dir(submission_id)

        container = None
        try:
            t0 = time.perf_counter()
            container = self.client.containers.run(
                self.sandbox_image,
                command=["compile_cpp", "/workspace/main.cpp", "/artifacts/main.bin"],
                volumes={
                    tmpdir: {"bind": "/workspace", "mode": "ro"},
                    str(artifact_dir): {"bind": "/artifacts", "mode": "rw"},
                },
                network_disabled=True,
                detach=True,
                mem_limit="256m",
                pids_limit=64,
            )
            result = container.wait()
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            stderr = container.logs(stdout=False, stderr=True).decode()

            if result.get("StatusCode", 1) != 0:
                return ExecutionResult(
                    status="compilation_error",
                    compile_time_ms=elapsed_ms,
                    stderr=stderr,
                )
            return ExecutionResult(status="compiled", compile_time_ms=elapsed_ms)
        except Exception as exc:
            return ExecutionResult(status="internal_error", stderr=str(exc))
        finally:
            if container:
                self._remove_container(container)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def judge(self, submission_id: str, test_inputs: list[str]) -> ExecutionResult:
        artifact_dir = self._artifact_dir(submission_id)
        binary = artifact_dir / "main.bin"
        if not binary.exists():
            return ExecutionResult(status="internal_error", stderr="Artifact missing")

        total_ms = 0
        for tc_input in test_inputs:
            input_dir = tempfile.mkdtemp(prefix="exp_tc_")
            (Path(input_dir) / "input.txt").write_text(tc_input, encoding="utf-8")
            container = None
            try:
                t0 = time.perf_counter()
                container = self.client.containers.run(
                    self.sandbox_image,
                    command=["run_binary", f"/artifacts/{binary.name}", "/inputs/input.txt"],
                    volumes={
                        str(artifact_dir): {"bind": "/artifacts", "mode": "ro"},
                        input_dir: {"bind": "/inputs", "mode": "ro"},
                    },
                    network_disabled=True,
                    detach=True,
                    mem_limit="256m",
                    pids_limit=64,
                )
                container.wait()
                total_ms += int((time.perf_counter() - t0) * 1000)
            finally:
                if container:
                    self._remove_container(container)
                shutil.rmtree(input_dir, ignore_errors=True)

        return ExecutionResult(status="accepted", judge_time_ms=total_ms)


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_executor() -> SimulatedExecutor | DockerExecutor:
    if EXECUTION_MODE == "docker":
        return DockerExecutor()
    return SimulatedExecutor()
