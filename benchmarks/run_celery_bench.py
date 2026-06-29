"""Celery benchmark runner.

Usage:
    python benchmarks/run_celery_bench.py \
        --run-id celery-4w-100s \
        --submissions 100 \
        --workers 4 \
        --output /results/celery_4w_100s.json

This script:
  1. Creates ExperimentSubmission records in the DB.
  2. Dispatches compile tasks to the Celery broker.
  3. Polls the DB until all submissions reach status='done'.
  4. Computes throughput and latency metrics.
  5. Writes results to a JSON file and appends a row to CSV.

The Celery workers must already be running when this script executes.
Use docker-compose to start them before calling this script.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import select, func, delete

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common.config import TESTCASES_PER_PROBLEM
from common.database import AsyncSessionLocal, create_tables
from common.models import ExperimentSubmission
from common.workload import build_problem_pool, generate_submissions


async def _create_records(submissions, run_id: str, num_workers: int) -> None:
    await create_tables()
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ExperimentSubmission).where(ExperimentSubmission.run_id == run_id)
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        for sub in submissions:
            record = ExperimentSubmission(
                id=sub.submission_id,
                run_id=run_id,
                framework="celery",
                num_workers=num_workers,
                status="queued",
            )
            session.add(record)
        await session.commit()


async def _poll_completion(
    run_id: str, n_total: int, poll_interval: float = 1.0, timeout_s: float = 1800.0
) -> None:
    print(f"[Celery] Polling for completion of {n_total} submissions (run_id={run_id})...")
    elapsed = 0.0
    while True:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count()).where(
                    ExperimentSubmission.run_id == run_id,
                    ExperimentSubmission.status == "done",
                )
            )
            done_count = result.scalar_one()
        if done_count >= n_total:
            print(f"[Celery] All {n_total} submissions done.")
            break
        if elapsed >= timeout_s:
            print(f"[Celery] TIMEOUT after {timeout_s}s: {done_count}/{n_total} done. Aborting.")
            break
        print(f"[Celery] Progress: {done_count}/{n_total} (elapsed: {elapsed:.0f}s)")
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval


async def _collect_metrics(run_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExperimentSubmission).where(
                ExperimentSubmission.run_id == run_id
            )
        )
        rows = result.scalars().all()

    total_times = sorted(
        r.total_time_ms for r in rows if r.total_time_ms is not None
    )
    n = len(total_times)

    def pct(p: float) -> float:
        if not total_times:
            return 0.0
        idx = int(n * p / 100)
        return float(total_times[min(idx, n - 1)])

    return {
        "latency_p50_ms": pct(50),
        "latency_p90_ms": pct(90),
        "latency_p99_ms": pct(99),
        "latency_mean_ms": round(sum(total_times) / n, 1) if n else 0,
        "n_done": n,
    }


def main():
    parser = argparse.ArgumentParser(description="Celery benchmark runner")
    parser.add_argument("--run-id",      default="celery-run-1")
    parser.add_argument("--submissions", type=int, default=100)
    parser.add_argument("--workers",     type=int, default=4)
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--output",      default="/results/celery_result.json")
    parser.add_argument("--csv",         default="/results/results.csv")
    args = parser.parse_args()

    problem_pool = build_problem_pool()
    submissions = generate_submissions(args.submissions, problem_pool, seed=args.seed)

    asyncio.run(_create_records(submissions, args.run_id, args.workers))

    # Dispatch compile tasks
    from celery_impl.compile_task import compile_submission
    wall_start = time.perf_counter()

    for sub in submissions:
        compile_submission.apply_async(
            args=[sub.submission_id, args.run_id],
            queue="exp-compile",
        )

    print(f"[Celery] Dispatched {len(submissions)} compile tasks.")
    asyncio.run(_poll_completion(args.run_id, args.submissions))
    wall_elapsed = time.perf_counter() - wall_start

    latency_metrics = asyncio.run(_collect_metrics(args.run_id))

    metrics = {
        "run_id": args.run_id,
        "framework": "celery",
        "num_workers": args.workers,
        "n_submissions": args.submissions,
        "wall_time_s": round(wall_elapsed, 3),
        "throughput_per_s": round(args.submissions / wall_elapsed, 3),
        **latency_metrics,
    }

    print(json.dumps(metrics, indent=2))
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)

    # Append to aggregate CSV
    csv_exists = os.path.exists(args.csv)
    with open(args.csv, "a", newline="") as csvf:
        fieldnames = list(metrics.keys())
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
        writer.writerow(metrics)

    print(f"[Celery] Results written to {args.output} and {args.csv}")


if __name__ == "__main__":
    main()
