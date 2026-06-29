"""SQLAlchemy model for tracking experiment submission lifecycle."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, func
from common.database import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class ExperimentSubmission(Base):
    """Tracks every submission dispatched during a benchmark run.

    Both Celery and Ray implementations write to this table so results
    are directly comparable by run_id.
    """
    __tablename__ = "experiment_submissions"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    run_id = Column(String(100), nullable=False, index=True)
    framework = Column(String(20), nullable=False)       # 'celery' | 'ray'
    num_workers = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="queued")

    # Lifecycle timestamps (UTC)
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    compile_started_at = Column(DateTime(timezone=True))
    compile_finished_at = Column(DateTime(timezone=True))
    judge_started_at = Column(DateTime(timezone=True))
    judge_finished_at = Column(DateTime(timezone=True))

    # Outcome
    verdict = Column(String(50))                         # 'accepted' | 'wrong_answer' | etc.

    # Derived durations (milliseconds) – written when judging completes
    queue_time_ms = Column(Integer)    # queued → compile_started
    compile_time_ms = Column(Integer)  # compile_started → compile_finished
    judge_time_ms = Column(Integer)    # judge_started → judge_finished
    total_time_ms = Column(Integer)    # queued → judge_finished
