"""Generate figures from collected CSV results.

Usage:
    python benchmarks/plot_results.py \
        --results-csv /results/results.csv \
        --sys-csv /results/sys_metrics_*.csv \
        --output-dir /results/figures

Generates:
  01_throughput_vs_workers.pdf   – Throughput (submissions/s) vs #workers
  02_latency_p50_p90_p99.pdf     – Latency percentiles vs #workers
  03_speedup_vs_workers.pdf      – Speedup relative to 1 worker (both frameworks)
  04_parallel_efficiency.pdf     – Speedup / num_workers
  05_cpu_utilization.pdf         – CPU% time-series (one line per run)
  06_power_consumption.pdf       – Average power (W) vs #workers
  07_memory_usage.pdf            – Peak memory vs #workers

All figures use the same style:
  - Celery: blue solid line with circles
  - Ray:    red dashed line with squares
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

import csv
import json
from collections import defaultdict
from pathlib import Path


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib", file=sys.stderr)
        sys.exit(1)


def load_results(csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: _auto_cast(v) for k, v in row.items()})
    return rows


def _auto_cast(v: str):
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def load_sys_metrics(pattern: str) -> list[dict]:
    rows = []
    for path in glob.glob(pattern):
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k: _auto_cast(v) for k, v in row.items()})
    return rows


def pivot_by_framework(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["framework"]].append(r)
    return dict(grouped)


def fig_throughput(rows: list[dict], out_dir: str, plt) -> None:
    fw = pivot_by_framework(rows)
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, style, marker in [("celery", "b-o", "o"), ("ray", "r--s", "s")]:
        data = sorted(fw.get(name, []), key=lambda r: r["num_workers"])
        if not data:
            continue
        xs = [r["num_workers"] for r in data]
        ys = [r["throughput_per_s"] for r in data]
        ax.plot(xs, ys, style, label=name.capitalize(), markersize=7)
    ax.set_xlabel("Número de workers")
    ax.set_ylabel("Throughput (envíos/s)")
    ax.set_title("Throughput vs. Número de Workers")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    path = os.path.join(out_dir, "01_throughput_vs_workers.pdf")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig_latency(rows: list[dict], out_dir: str, plt) -> None:
    fw = pivot_by_framework(rows)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=False)
    percentiles = [("latency_p50_ms", "P50"), ("latency_p90_ms", "P90"), ("latency_p99_ms", "P99")]
    for ax, (col, label) in zip(axes, percentiles):
        for name, style in [("celery", "b-o"), ("ray", "r--s")]:
            data = sorted(fw.get(name, []), key=lambda r: r["num_workers"])
            if not data:
                continue
            xs = [r["num_workers"] for r in data]
            ys = [r[col] for r in data]
            ax.plot(xs, ys, style, label=name.capitalize(), markersize=7)
        ax.set_xlabel("Workers")
        ax.set_ylabel("Latencia (ms)")
        ax.set_title(label)
        ax.legend(fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.5)
    fig.suptitle("Latencia (P50 / P90 / P99) vs. Número de Workers")
    path = os.path.join(out_dir, "02_latency_p50_p90_p99.pdf")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig_speedup(rows: list[dict], out_dir: str, plt) -> None:
    fw = pivot_by_framework(rows)
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, style in [("celery", "b-o"), ("ray", "r--s")]:
        data = sorted(fw.get(name, []), key=lambda r: r["num_workers"])
        if not data:
            continue
        base = next((r["throughput_per_s"] for r in data if r["num_workers"] == 1), None)
        if base is None or base == 0:
            continue
        xs = [r["num_workers"] for r in data]
        ys = [r["throughput_per_s"] / base for r in data]
        ax.plot(xs, ys, style, label=name.capitalize(), markersize=7)

    # Ideal linear speedup reference
    max_w = max((r["num_workers"] for r in rows), default=1)
    ax.plot([1, max_w], [1, max_w], "k:", label="Ideal lineal")
    ax.set_xlabel("Número de workers")
    ax.set_ylabel("Speedup (vs. 1 worker)")
    ax.set_title("Speedup vs. Número de Workers")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    path = os.path.join(out_dir, "03_speedup_vs_workers.pdf")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig_efficiency(rows: list[dict], out_dir: str, plt) -> None:
    fw = pivot_by_framework(rows)
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, style in [("celery", "b-o"), ("ray", "r--s")]:
        data = sorted(fw.get(name, []), key=lambda r: r["num_workers"])
        if not data:
            continue
        base = next((r["throughput_per_s"] for r in data if r["num_workers"] == 1), None)
        if base is None or base == 0:
            continue
        xs = [r["num_workers"] for r in data]
        ys = [r["throughput_per_s"] / base / r["num_workers"] for r in data]
        ax.plot(xs, ys, style, label=name.capitalize(), markersize=7)
    ax.axhline(1.0, color="k", linestyle=":", label="Eficiencia ideal")
    ax.set_xlabel("Número de workers")
    ax.set_ylabel("Eficiencia paralela (speedup / #workers)")
    ax.set_title("Eficiencia Paralela")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    path = os.path.join(out_dir, "04_parallel_efficiency.pdf")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig_power(sys_rows: list[dict], bench_rows: list[dict], out_dir: str, plt) -> None:
    if not sys_rows:
        print("  No sys metrics available for power figure.")
        return

    # Average power per run_id → join with num_workers and framework from bench_rows
    run_info = {r["run_id"]: r for r in bench_rows}
    power_by_run: dict[str, list[float]] = defaultdict(list)
    for row in sys_rows:
        rid = row.get("run_id", "")
        pw = row.get("power_w", "")
        if pw != "" and pw is not None:
            power_by_run[rid].append(float(pw))

    # Group by framework
    celery_pts, ray_pts = [], []
    for rid, powers in power_by_run.items():
        if not powers:
            continue
        avg = sum(powers) / len(powers)
        info = run_info.get(rid, {})
        fw = info.get("framework", "")
        nw = info.get("num_workers", 0)
        if fw == "celery":
            celery_pts.append((nw, avg))
        elif fw == "ray":
            ray_pts.append((nw, avg))

    fig, ax = plt.subplots(figsize=(7, 4))
    for pts, style, label in [(celery_pts, "b-o", "Celery"), (ray_pts, "r--s", "Ray")]:
        if pts:
            pts.sort()
            xs, ys = zip(*pts)
            ax.plot(xs, ys, style, label=label, markersize=7)
    ax.set_xlabel("Número de workers")
    ax.set_ylabel("Potencia promedio (W)")
    ax.set_title("Consumo de Potencia vs. Número de Workers")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    path = os.path.join(out_dir, "06_power_consumption.pdf")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark figures")
    parser.add_argument("--results-csv",  default="/results/results.csv")
    parser.add_argument("--sys-csv",      default="/results/sys_metrics_*.csv")
    parser.add_argument("--output-dir",   default="/results/figures")
    args = parser.parse_args()

    plt = _require_matplotlib()

    if not os.path.exists(args.results_csv):
        print(f"ERROR: {args.results_csv} not found.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    rows = load_results(args.results_csv)
    sys_rows = load_sys_metrics(args.sys_csv)

    print(f"Loaded {len(rows)} benchmark rows, {len(sys_rows)} sys-metric rows.")
    print("Generating figures...")

    fig_throughput(rows, args.output_dir, plt)
    fig_latency(rows, args.output_dir, plt)
    fig_speedup(rows, args.output_dir, plt)
    fig_efficiency(rows, args.output_dir, plt)
    fig_power(sys_rows, rows, args.output_dir, plt)

    print("Done.")


if __name__ == "__main__":
    main()
