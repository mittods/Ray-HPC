"""Ray remote function for judging.

Design rationale:
  - The function accepts `compile_result` as a plain dict (not an ObjectRef).
    The driver chains futures by first calling ray.get(compile_ref) and then
    submitting judge_submission.remote(compile_result, ...) to keep the
    dependency explicit and avoid hidden waits inside the worker.
  - Alternatively, passing the ObjectRef directly would work too (Ray
    auto-resolves dependencies), but using explicit ray.get() in the driver
    follows the pattern from the class examples (see ray_demo_complete.py).
  - num_cpus=1 ensures each judge task claims one CPU slot.

Return value schema:
  {
    "submission_id": str,
    "verdict": str,
    "judge_time_ms": int,
    "total_time_ms": int,
  }
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

import ray

from common.executor import get_executor


def _now() -> datetime:
    return datetime.now(timezone.utc)


@ray.remote(num_cpus=1)
def judge_submission(
    compile_result: dict,
    run_id: str,
    n_testcases: int,
) -> dict:
    """Run a compiled submission against synthetic test cases."""
    import asyncio as _asyncio
    from sqlalchemy import select
    from common.database import AsyncSessionLocal
    from common.models import ExperimentSubmission

    submission_id: str = compile_result["submission_id"]
    compile_status: str = compile_result["status"]

    # If compilation failed, skip judging and mark done immediately
    if compile_status != "compiled":
        return {
            "submission_id": submission_id,
            "verdict": compile_status,
            "judge_time_ms": 0,
            "total_time_ms": compile_result.get("compile_time_ms", 0),
        }

    async def _start():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = res.scalar_one_or_none()
            if sub:
                sub.status = "running"
                sub.judge_started_at = _now()
                await session.commit()
                return sub.queued_at
            return None

    queued_at = _asyncio.run(_start())

    executor = get_executor()
    exec_result = executor.judge(submission_id, n_testcases)

    now = _now()

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

            sub.judge_finished_at = now
            sub.judge_time_ms = exec_result.judge_time_ms
            sub.status = "done"
            sub.verdict = exec_result.status

            if queued_at and sub.compile_started_at:
                q_delta = sub.compile_started_at - queued_at
                sub.queue_time_ms = int(q_delta.total_seconds() * 1000)

            if queued_at:
                total_delta = now - queued_at
                sub.total_time_ms = int(total_delta.total_seconds() * 1000)

            await session.commit()

    _asyncio.run(_finish())

    total_ms = 0
    if queued_at:
        total_ms = int((now - queued_at).total_seconds() * 1000)

    return {
        "submission_id": submission_id,
        "verdict": exec_result.status,
        "judge_time_ms": exec_result.judge_time_ms,
        "total_time_ms": total_ms,
    }
