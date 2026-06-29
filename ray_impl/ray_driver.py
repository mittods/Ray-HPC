"""Ray driver for the experimental judge pipeline.

This module is the entry point for the Ray-based benchmark run.
It is NOT a long-running service (unlike Celery workers); instead it is an
active driver that submits all jobs, waits for them, and then exits.

Programming model (consistent with course examples):
  1. Initialize Ray with ray.init() – autodetects CPUs as in main02.py.
  2. Submit compile tasks for all submissions – returns a list of ObjectRefs.
  3. For each completed compile task, submit the corresponding judge task.
     We use ray.wait() to process results as they arrive, matching the
     progress-monitoring pattern from Factorizacion.py and ray_demo_complete.py.
  4. Collect all judge results with ray.get().
  5. Shutdown Ray and return the aggregated metrics.

Concurrency control:
  NUM_WORKERS controls the effective parallelism via num_cpus in ray.init().
  Setting num_cpus=N gives Ray a budget of N CPU slots; since each task
  requests num_cpus=1, at most N tasks run simultaneously.
"""
from __future__ import annotations
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import ray

from common.config import RAY_ADDRESS, RAY_NUM_CPUS, TESTCASES_PER_PROBLEM
from common.database import AsyncSessionLocal, create_tables
from common.models import ExperimentSubmission
from common.workload import build_problem_pool, generate_submissions
from ray_impl.compile_remote import compile_submission
from ray_impl.judge_remote import judge_submission


def init_ray(num_cpus: int | None = None) -> None:
    """Initialize Ray, detecting available CPUs when num_cpus is not specified.

    Follows the initialization pattern from the course examples:
        ray.init(ignore_reinit_error=True)
    with an optional explicit CPU budget for scalability experiments.
    """
    effective_cpus = num_cpus or (RAY_NUM_CPUS if RAY_NUM_CPUS > 0 else None)

    if RAY_ADDRESS == "auto" or RAY_ADDRESS == "":
        ray.init(
            ignore_reinit_error=True,
            num_cpus=effective_cpus,
            include_dashboard=False,
        )
    else:
        # Connect to an existing cluster (multi-node deployment)
        ray.init(address=RAY_ADDRESS, ignore_reinit_error=True)

    cpus = int(ray.cluster_resources().get("CPU", 0))
    print(f"[Ray] Initialized – cluster resources: {ray.cluster_resources()}")
    print(f"[Ray] Effective CPU slots: {cpus}")


async def _create_submission_records(
    submissions: list[Any],
    run_id: str,
    framework: str,
    num_workers: int,
) -> None:
    await create_tables()
    async with AsyncSessionLocal() as session:
        for sub in submissions:
            record = ExperimentSubmission(
                id=sub.submission_id,
                run_id=run_id,
                framework=framework,
                num_workers=num_workers,
                status="queued",
            )
            session.add(record)
        await session.commit()


def run_benchmark(
    run_id: str,
    n_submissions: int,
    num_workers: int,
    seed: int = 42,
) -> dict:
    """Execute a complete benchmark run.

    Parameters
    ----------
    run_id:        Unique identifier for this run (stored in every DB row).
    n_submissions: Total number of synthetic submissions to process.
    num_workers:   CPU slots available to Ray (controls parallelism).
    seed:          Random seed for deterministic workload generation.

    Returns
    -------
    A dict with aggregate metrics: throughput, latency percentiles, etc.
    """
    init_ray(num_cpus=num_workers)

    problem_pool = build_problem_pool()
    submissions = generate_submissions(n_submissions, problem_pool, seed=seed)

    # Persist initial records so the benchmark collector can track state
    asyncio.run(
        _create_submission_records(
            submissions, run_id, framework="ray", num_workers=num_workers
        )
    )

    wall_start = time.perf_counter()

    # ── Phase 1: submit all compile tasks ────────────────────────────────────
    # Pattern from main02.py / ray_demo_complete.py: build a list of futures,
    # then process completions with ray.wait().
    compile_futures = [
        compile_submission.remote(
            sub.submission_id,
            sub.problem.source_code,
            run_id,
        )
        for sub in submissions
    ]

    print(f"[Ray] Submitted {len(compile_futures)} compile tasks.")

    # ── Phase 2: as each compile finishes, chain a judge task ────────────────
    # ray.wait() returns as soon as at least one future is ready.
    # This avoids blocking on all compilations before judging begins.
    pending_compile = list(compile_futures)
    judge_futures: list = []
    compile_completed = 0

    while pending_compile:
        ready, pending_compile = ray.wait(pending_compile, num_returns=1, timeout=60.0)
        for ref in ready:
            compile_result = ray.get(ref)
            compile_completed += 1

            # Chain judge task immediately – no waiting for other compiles
            judge_ref = judge_submission.remote(
                compile_result,
                run_id,
                TESTCASES_PER_PROBLEM,
            )
            judge_futures.append(judge_ref)

    print(f"[Ray] All {compile_completed} compile tasks done. Waiting for {len(judge_futures)} judge tasks.")

    # ── Phase 3: collect all judge results ───────────────────────────────────
    pending_judge = list(judge_futures)
    results: list[dict] = []
    judge_completed = 0

    while pending_judge:
        ready, pending_judge = ray.wait(pending_judge, num_returns=1, timeout=120.0)
        for ref in ready:
            result = ray.get(ref)
            results.append(result)
            judge_completed += 1
            if judge_completed % 10 == 0 or judge_completed == n_submissions:
                print(f"[Ray] Judge progress: {judge_completed}/{n_submissions}")

    wall_elapsed = time.perf_counter() - wall_start

    ray.shutdown()
    print("[Ray] Shutdown complete.")

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    total_times = [r["total_time_ms"] for r in results if r.get("total_time_ms")]
    total_times.sort()
    n = len(total_times)

    def percentile(data: list[int], p: float) -> float:
        if not data:
            return 0.0
        idx = int(len(data) * p / 100)
        return data[min(idx, len(data) - 1)]

    metrics = {
        "run_id": run_id,
        "framework": "ray",
        "num_workers": num_workers,
        "n_submissions": n_submissions,
        "wall_time_s": round(wall_elapsed, 3),
        "throughput_per_s": round(n_submissions / wall_elapsed, 3),
        "latency_p50_ms": percentile(total_times, 50),
        "latency_p90_ms": percentile(total_times, 90),
        "latency_p99_ms": percentile(total_times, 99),
        "latency_mean_ms": round(sum(total_times) / n, 1) if n else 0,
    }
    return metrics


if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Ray benchmark driver")
    parser.add_argument("--run-id",       default="ray-run-1")
    parser.add_argument("--submissions",  type=int, default=100)
    parser.add_argument("--workers",      type=int, default=4)
    parser.add_argument("--seed",         type=int, default=42)
    parser.add_argument("--output",       default="/results/ray_result.json")
    args = parser.parse_args()

    metrics = run_benchmark(
        run_id=args.run_id,
        n_submissions=args.submissions,
        num_workers=args.workers,
        seed=args.seed,
    )
    print(json.dumps(metrics, indent=2))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)
