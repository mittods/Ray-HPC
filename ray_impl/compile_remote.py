"""Ray remote function for compilation.

Design rationale (aligned with course material):
  - @ray.remote turns the function into a distributed task, consistent with
    the pattern shown in main00.py and main02.py from the class examples.
  - num_cpus=1 is declared explicitly so Ray's scheduler accounts for resource
    consumption (see presentacion.txt: "Ray puede indicar cuántos recursos
    necesita cada tarea").
  - The function is pure (no shared mutable state) and returns a plain dict
    so results can be retrieved with ray.get() without serialization issues.

Return value schema:
  {
    "submission_id": str,
    "status": "compiled" | "compilation_error" | "internal_error",
    "compile_time_ms": int,
    "artifact_dir": str,      # only present when status == "compiled"
  }
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

import ray

from common.executor import get_executor
from common.runtime import write_submission_manifest


def _now() -> datetime:
    return datetime.now(timezone.utc)


@ray.remote(num_cpus=1)
def compile_submission(
    submission_id: str,
    source_code: str,
    run_id: str,
) -> dict:
    """Compile a single submission.  Runs inside a Ray worker process."""
    # Lazy DB import – each Ray worker is a separate OS process; connection
    # pools must be created inside the worker, not in the driver.
    import asyncio as _asyncio
    from sqlalchemy import select
    from common.database import AsyncSessionLocal
    from common.models import ExperimentSubmission

    async def _mark_compiling():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = res.scalar_one_or_none()
            if sub:
                sub.status = "compiling"
                sub.compile_started_at = _now()
                await session.commit()

    _asyncio.run(_mark_compiling())

    executor = get_executor()
    exec_result = executor.compile(submission_id)

    async def _finish():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = res.scalar_one_or_none()
            if not sub:
                return

            sub.compile_finished_at = _now()
            sub.compile_time_ms = exec_result.compile_time_ms

            if exec_result.status != "compiled":
                sub.status = "compilation_error"
                sub.verdict = "compilation_error"
                if sub.queued_at and sub.compile_finished_at:
                    delta = sub.compile_finished_at - sub.queued_at
                    sub.total_time_ms = int(delta.total_seconds() * 1000)
            else:
                write_submission_manifest(
                    submission_id, {"kind": "compiled", "entrypoint": "main.bin"}
                )
                sub.status = "compiled"

            await session.commit()

    _asyncio.run(_finish())

    from common.runtime import submission_artifact_dir
    return {
        "submission_id": submission_id,
        "status": exec_result.status,
        "compile_time_ms": exec_result.compile_time_ms,
        "artifact_dir": str(submission_artifact_dir(submission_id)),
    }
