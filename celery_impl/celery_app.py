"""Celery application for the experiment baseline.

Architecture mirrors the production system:
  - Two queues: 'exp-compile' and 'exp-judge'
  - worker_prefetch_multiplier=1 for fair task distribution
  - task_acks_late=True to prevent task loss on worker crash

The production fair-scheduler (Redis-based per-user slot) is intentionally
omitted here to keep the experiment focused on framework-level throughput
and latency under controlled, homogeneous load.
"""
from celery import Celery
from common.config import REDIS_URL

celery_app = Celery("exp_judge", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "celery_impl.compile_task.*": {"queue": "exp-compile"},
        "celery_impl.judge_task.*": {"queue": "exp-judge"},
    },
    result_expires=3600,
)

celery_app.autodiscover_tasks(["celery_impl"])
