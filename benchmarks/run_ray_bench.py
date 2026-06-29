"""Ray benchmark runner.

Usage:
    python benchmarks/run_ray_bench.py \
        --run-id ray-4w-100s \
        --submissions 100 \
        --workers 4 \
        --output /results/ray_4w_100s.json

Delegates to ray_impl/ray_driver.py which handles initialization,
task submission, and progress monitoring.  This script adds CSV output.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ray_impl.ray_driver import run_benchmark


def main():
    parser = argparse.ArgumentParser(description="Ray benchmark runner")
    parser.add_argument("--run-id",      default="ray-run-1")
    parser.add_argument("--submissions", type=int, default=100)
    parser.add_argument("--workers",     type=int, default=4)
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--output",      default="/results/ray_result.json")
    parser.add_argument("--csv",         default="/results/results.csv")
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

    csv_exists = os.path.exists(args.csv)
    with open(args.csv, "a", newline="") as csvf:
        fieldnames = list(metrics.keys())
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
        writer.writerow(metrics)

    print(f"[Ray] Results written to {args.output} and {args.csv}")


if __name__ == "__main__":
    main()
