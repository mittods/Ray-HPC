"""RAPL power measurement wrapper.

Supports:
  - Intel RAPL via /sys/class/powercap/intel-rapl
  - AMD RAPL via /sys/class/powercap (kernel ≥ 5.18 on Zen 3+)
  - Fallback: perf stat -e power/energy-pkg/ (requires perf installed)

Design choice: the sysfs RAPL interface is preferred over perf because:
  1. It does not require root privileges (on most distros the files are readable
     by default or by adding the user to the 'power' group).
  2. It provides a direct cumulative energy counter (µJ) with µs resolution.
  3. It is reproducible: the same kernel counter is read by all tools.
  4. perf has measurement overhead and requires elevated privileges.

For AMD Ryzen Threadripper PRO 5975WX (Zen 3):
  The kernel exposes the package energy via:
    /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj
  (yes, the path uses "intel-rapl" even on AMD – this is the RAPL subsystem
   shared with AMD starting from Linux kernel 5.13).

Reference:
  https://www.kernel.org/doc/html/latest/power/powercap/powercap.html
"""
from __future__ import annotations
import subprocess
import time
from pathlib import Path


# ─── Sysfs path detection ─────────────────────────────────────────────────────

def _find_energy_file() -> Path | None:
    candidates = [
        # Standard Intel/AMD RAPL via powercap
        Path("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"),
        Path("/sys/class/powercap/intel-rapl:0/energy_uj"),
    ]
    for c in candidates:
        if c.exists():
            return c

    # Generic search
    for p in Path("/sys/class/powercap").glob("*/energy_uj"):
        return p

    return None


_ENERGY_FILE: Path | None = _find_energy_file()
_MAX_ENERGY_RANGE_FILE: Path | None = (
    _ENERGY_FILE.parent / "max_energy_range_uj" if _ENERGY_FILE else None
)


def is_rapl_available() -> bool:
    return _ENERGY_FILE is not None and _ENERGY_FILE.exists()


def read_energy_uj() -> int | None:
    """Read the current cumulative energy counter in microjoules."""
    if _ENERGY_FILE is None:
        return None
    try:
        return int(_ENERGY_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def max_energy_range_uj() -> int:
    """Return the counter overflow value (wraps to 0 after this)."""
    if _MAX_ENERGY_RANGE_FILE and _MAX_ENERGY_RANGE_FILE.exists():
        try:
            return int(_MAX_ENERGY_RANGE_FILE.read_text().strip())
        except (OSError, ValueError):
            pass
    return 2**32  # safe default


def measure_power_w(duration_s: float = 1.0) -> float | None:
    """Measure average power in Watts over `duration_s` seconds.

    Returns None if RAPL is not available.
    """
    e0 = read_energy_uj()
    if e0 is None:
        return None
    t0 = time.perf_counter()
    time.sleep(duration_s)
    e1 = read_energy_uj()
    t1 = time.perf_counter()

    if e1 is None:
        return None

    delta_uj = e1 - e0
    if delta_uj < 0:
        # Counter wrap
        delta_uj += max_energy_range_uj()

    elapsed = t1 - t0
    return round(delta_uj / (elapsed * 1_000_000), 2)  # µJ / (s * 1e6) = W


# ─── perf stat fallback ───────────────────────────────────────────────────────

def measure_power_perf(duration_s: float = 1.0) -> float | None:
    """Use 'perf stat -e power/energy-pkg/' to measure package power.

    Requires: perf installed, and either root or /proc/sys/kernel/perf_event_paranoid <= 0.
    Returns None on failure.
    """
    try:
        result = subprocess.run(
            [
                "perf", "stat",
                "-e", "power/energy-pkg/",
                "--",
                "sleep", str(duration_s),
            ],
            capture_output=True,
            text=True,
            timeout=duration_s + 5,
        )
        for line in (result.stdout + result.stderr).splitlines():
            if "Joules" in line or "energy-pkg" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if "Joule" in p and i > 0:
                        joules_str = parts[i - 1].replace(",", ".")
                        try:
                            joules = float(joules_str)
                            return round(joules / duration_s, 2)
                        except ValueError:
                            pass
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def best_measure_power(duration_s: float = 1.0) -> dict:
    """Try RAPL sysfs first; fall back to perf stat.

    Returns:
        {"method": str, "power_w": float | None}
    """
    if is_rapl_available():
        pw = measure_power_w(duration_s)
        return {"method": "rapl_sysfs", "power_w": pw}

    pw = measure_power_perf(duration_s)
    return {"method": "perf_stat", "power_w": pw}


if __name__ == "__main__":
    import json
    print(f"RAPL file: {_ENERGY_FILE}")
    print(f"Available: {is_rapl_available()}")
    result = best_measure_power(duration_s=2.0)
    print(json.dumps(result, indent=2))
