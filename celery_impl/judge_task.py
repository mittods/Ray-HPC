"""Celery judge task (experiment baseline).

Flow:
  1. Mark submission as 'running' in the DB.
  2. Run executor.judge() for n_testcases test cases.
  3. Persist verdict and timing metrics.
  4. Compute all derived durations (queue_time_ms, total_time_ms).
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from celery_impl.celery_app import celery_app
from common.database import AsyncSessionLocal
from common.executor import get_executor
from common.models import ExperimentSubmission


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(
    bind=True,
    name="celery_impl.judge_task.judge_submission",
    queue="exp-judge",
)
def judge_submission(self, submission_id: str, run_id: str, n_testcases: int):
    """Run a compiled submission against synthetic test cases."""

    async def _start():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExperimentSubmission).where(
                    ExperimentSubmission.id == submission_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub is None:
                return None
            sub.status = "running"
            sub.judge_started_at = _now()
            await session.commit()
            return sub.queued_at, sub.compile_time_ms

    timing = asyncio.run(_start())
    if timing is None:
        return

    queued_at, compile_time_ms = timing
    executor = get_executor()
    exec_result = executor.judge(submission_id, n_testcases)

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

            now = _now()
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

    asyncio.run(_finish())
