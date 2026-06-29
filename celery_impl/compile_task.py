"""Celery compile task (experiment baseline).

Flow:
  1. Mark submission as 'compiling' in the DB.
  2. Run the executor's compile() (simulated or Docker).
  3. On success, persist the artifact manifest and dispatch judge_task.
  4. On failure, mark submission as 'compilation_error'.

Metrics (timestamps) are written to the ExperimentSubmission row so the
benchmark collector can compute queue_time_ms and compile_time_ms.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from celery_impl.celery_app import celery_app
from common.config import TESTCASES_PER_PROBLEM
from common.database import AsyncSessionLocal
from common.executor import get_executor
from common.models import ExperimentSubmission
from common.runtime import write_submission_manifest


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(
    bind=True,
    name="celery_impl.compile_task.compile_submission",
    queue="exp-compile",
)
def compile_submission(self, submission_id: str, run_id: str):
    """Compile a synthetic submission and chain to judge_submission."""

    async def _run():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub is None:
                return

            sub.status = "compiling"
            sub.compile_started_at = _now()
            await session.commit()

    asyncio.run(_run())

    executor = get_executor()
    exec_result = executor.compile(submission_id)

    async def _finish():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub is None:
                return

            sub.compile_finished_at = _now()
            sub.compile_time_ms = exec_result.compile_time_ms

            if exec_result.status != "compiled":
                sub.status = "compilation_error"
                sub.verdict = "compilation_error"
                if sub.queued_at and sub.compile_finished_at:
                    delta = sub.compile_finished_at - sub.queued_at
                    sub.total_time_ms = int(delta.total_seconds() * 1000)
                await session.commit()
                return

            write_submission_manifest(submission_id, {"kind": "compiled", "entrypoint": "main.bin"})
            sub.status = "compiled"
            await session.commit()

    asyncio.run(_finish())

    if exec_result.status == "compiled":
        from celery_impl.judge_task import judge_submission
        judge_submission.apply_async(
            args=[submission_id, run_id, TESTCASES_PER_PROBLEM],
            queue="exp-judge",
        )
