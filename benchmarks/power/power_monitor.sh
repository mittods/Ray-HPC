#!/usr/bin/env bash
# Continuous power monitoring wrapper.
# Wraps collect_metrics.py and additionally exports a perf report.
#
# Usage:
#   ./benchmarks/power/power_monitor.sh <run_id> <output_dir> &
#   MONITOR_PID=$!
#   # ... run benchmark ...
#   kill $MONITOR_PID
#
# Output files:
#   <output_dir>/sys_metrics_<run_id>.csv   – CPU, memory, RAPL power
#   <output_dir>/perf_<run_id>.txt          – perf stat summary (if available)

set -eu

RUN_ID="${1:-unknown}"
OUTPUT_DIR="${2:-/results}"
INTERVAL="${3:-1.0}"

mkdir -p "${OUTPUT_DIR}"

PYTHONPATH="${PYTHONPATH:-/experiment}" \
python /experiment/benchmarks/collect_metrics.py \
    --run-id "${RUN_ID}" \
    --interval "${INTERVAL}" \
    --output "${OUTPUT_DIR}/sys_metrics_${RUN_ID}.csv" &

COLLECTOR_PID=$!
echo "[power_monitor] collector PID: ${COLLECTOR_PID}"
echo "${COLLECTOR_PID}" > "${OUTPUT_DIR}/.collector_pid_${RUN_ID}"

# Optional: run perf stat in background capturing energy over the whole run
if command -v perf &>/dev/null; then
    perf stat \
        -e power/energy-pkg/,power/energy-ram/ \
        --log-fd 1 \
        -- bash -c "tail -f /dev/null" \
        > "${OUTPUT_DIR}/perf_${RUN_ID}.txt" 2>&1 &
    echo "[power_monitor] perf PID: $!"
    echo "$!" > "${OUTPUT_DIR}/.perf_pid_${RUN_ID}"
fi

# Wait for the collector (will run until killed)
wait "${COLLECTOR_PID}" || true
