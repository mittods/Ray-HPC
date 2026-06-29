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

# Direct imports register the tasks with this app before the worker boots.
# conf.update(imports=[...]) is unreliable in Celery 5.x — the worker reads
# conf before conf.update() runs, so those modules are never imported.
# Placing imports HERE (after celery_app is defined) avoids the circular
# import: compile_task.py imports celery_app, which is already defined above.
import celery_impl.compile_task  # noqa: F401, E402
import celery_impl.judge_task    # noqa: F401, E402
