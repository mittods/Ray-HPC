"""System metrics collector.

Samples CPU utilization, memory, and (if available) RAPL power
at a configurable interval and writes a time-series CSV.

Usage (run in background during a benchmark):
    python benchmarks/collect_metrics.py \
        --run-id celery-4w-100s \
        --interval 1.0 \
        --output /results/sys_metrics_celery_4w.csv &
    COLLECTOR_PID=$!
    # ... run benchmark ...
    kill $COLLECTOR_PID
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
import time
from pathlib import Path


# ─── CPU utilization via /proc/stat ──────────────────────────────────────────

def _read_cpu_stat() -> tuple[int, int]:
    """Return (idle, total) jiffies from /proc/stat for the first CPU line."""
    with open("/proc/stat") as f:
        line = f.readline()
    parts = line.split()
    # cpu  user nice system idle iowait irq softirq steal guest guest_nice
    values = [int(x) for x in parts[1:]]
    idle = values[3] + values[4]          # idle + iowait
    total = sum(values)
    return idle, total


def cpu_percent(prev_idle: int, prev_total: int, curr_idle: int, curr_total: int) -> float:
    d_idle = curr_idle - prev_idle
    d_total = curr_total - prev_total
    if d_total == 0:
        return 0.0
    return round((1 - d_idle / d_total) * 100, 2)


# ─── Memory via /proc/meminfo ─────────────────────────────────────────────────

def memory_mb() -> tuple[float, float]:
    """Return (used_mb, total_mb)."""
    info: dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
    total = info.get("MemTotal", 0) / 1024
    available = info.get("MemAvailable", 0) / 1024
    used = total - available
    return round(used, 1), round(total, 1)


# ─── RAPL power via sysfs ────────────────────────────────────────────────────

def _find_rapl_energy_file() -> Path | None:
    """Find the RAPL pkg energy counter file.

    Supports both Intel (/sys/class/powercap/intel-rapl) and AMD
    (/sys/class/powercap/amd_energy or hwmon).
    """
    # Intel RAPL (also available on some AMD via kernel ≥ 5.13)
    intel = Path("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj")
    if intel.exists():
        return intel

    # AMD RAPL via powercap (kernel ≥ 6.2 on Zen 3+)
    for p in Path("/sys/class/powercap").glob("*/energy_uj"):
        return p

    # hwmon fallback (some AMD chips expose power1_input in µW)
    for p in Path("/sys/class/hwmon").glob("hwmon*/power1_input"):
        return p

    return None


_RAPL_PATH: Path | None = _find_rapl_energy_file()
_RAPL_IS_ENERGY = _RAPL_PATH is not None and "energy_uj" in str(_RAPL_PATH)


def read_rapl_raw() -> int | None:
    if _RAPL_PATH is None:
        return None
    try:
        return int(_RAPL_PATH.read_text().strip())
    except Exception:
        return None


def rapl_power_w(prev_raw: int | None, curr_raw: int | None, elapsed_s: float) -> float | None:
    """Compute average power in Watts between two energy samples."""
    if prev_raw is None or curr_raw is None:
        return None
    if _RAPL_IS_ENERGY:
        # energy_uj in microjoules → Watts = Δenergy_µJ / (elapsed_s * 1e6)
        delta_uj = curr_raw - prev_raw
        if delta_uj < 0:
            # Counter wrap-around (rare for pkg domain)
            delta_uj += 2**32
        return round(delta_uj / (elapsed_s * 1_000_000), 2)
    else:
        # power1_input in µW → Watts
        return round(curr_raw / 1_000_000, 2)


# ─── Main collector loop ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="System metrics collector")
    parser.add_argument("--run-id",   default="unknown")
    parser.add_argument("--interval", type=float, default=1.0, help="Sample interval in seconds")
    parser.add_argument("--output",   default="/results/sys_metrics.csv")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    fieldnames = ["timestamp", "run_id", "cpu_pct", "mem_used_mb", "mem_total_mb", "power_w"]
    with open(args.output, "w", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()

        prev_idle, prev_total = _read_cpu_stat()
        prev_rapl = read_rapl_raw()
        prev_ts = time.perf_counter()

        print(f"[metrics] Collecting to {args.output} every {args.interval}s. RAPL: {_RAPL_PATH}")

        while True:
            time.sleep(args.interval)

            curr_idle, curr_total = _read_cpu_stat()
            curr_rapl = read_rapl_raw()
            curr_ts = time.perf_counter()
            elapsed = curr_ts - prev_ts

            cpu = cpu_percent(prev_idle, prev_total, curr_idle, curr_total)
            mem_used, mem_total = memory_mb()
            power = rapl_power_w(prev_rapl, curr_rapl, elapsed)

            row = {
                "timestamp": round(curr_ts, 3),
                "run_id": args.run_id,
                "cpu_pct": cpu,
                "mem_used_mb": mem_used,
                "mem_total_mb": mem_total,
                "power_w": power if power is not None else "",
            }
            writer.writerow(row)
            csvf.flush()

            prev_idle, prev_total = curr_idle, curr_total
            prev_rapl = curr_rapl
            prev_ts = curr_ts


if __name__ == "__main__":
    main()
