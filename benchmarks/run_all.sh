#!/usr/bin/env bash
# Master benchmark script.
# Runs all scenarios for both Celery and Ray, collecting system metrics
# throughout. Results are written to $RESULTS_DIR (default: ./results).
#
# Prerequisites:
#   - docker compose is installed
#   - The experiment images are built (docker compose build)
#   - The base infrastructure is running:
#       docker compose -f docker-compose.yml up -d
#
# Usage:
#   cd Di-Judge-Backend/experiments/ray
#   export RESULTS_DIR=./results
#   bash benchmarks/run_all.sh
#
# Scenario matrix:
#   Workers: 1, 2, 4, 8, 16, 32
#   Submissions: 100, 500
#   Frameworks: celery, ray
#
# Total runs: 2 * 6 * 2 = 24

set -eu

RESULTS_DIR="${RESULTS_DIR:-./results}"
LOG_DIR="${RESULTS_DIR}/logs"
mkdir -p "${RESULTS_DIR}" "${LOG_DIR}"

WORKERS_LIST="${WORKERS_LIST:-1 2 4 8 16 32}"
SUBMISSIONS_LIST="${SUBMISSIONS_LIST:-100 500}"
SEED=42

echo "[run_all] Starting experiment matrix. Results: ${RESULTS_DIR}"
echo "[run_all] Workers: ${WORKERS_LIST}"
echo "[run_all] Submissions: ${SUBMISSIONS_LIST}"
date

# ─── Helper: run one scenario ────────────────────────────────────────────────

run_scenario() {
    local FRAMEWORK="$1"
    local WORKERS="$2"
    local SUBMISSIONS="$3"
    local RUN_ID="${FRAMEWORK}-w${WORKERS}-s${SUBMISSIONS}"

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo " Framework: ${FRAMEWORK} | Workers: ${WORKERS} | Submissions: ${SUBMISSIONS}"
    echo " Run ID: ${RUN_ID}"
    echo "═══════════════════════════════════════════════════════════"

    # Start system metrics collector in background
    bash benchmarks/power/power_monitor.sh "${RUN_ID}" "${RESULTS_DIR}" &
    MONITOR_PID=$!

    if [ "${FRAMEWORK}" = "celery" ]; then
        bash benchmarks/scenarios/run_celery_scenario.sh \
            "${RUN_ID}" "${WORKERS}" "${SUBMISSIONS}" "${SEED}" \
            "${RESULTS_DIR}" \
            2>&1 | tee "${LOG_DIR}/${RUN_ID}.log"
    else
        bash benchmarks/scenarios/run_ray_scenario.sh \
            "${RUN_ID}" "${WORKERS}" "${SUBMISSIONS}" "${SEED}" \
            "${RESULTS_DIR}" \
            2>&1 | tee "${LOG_DIR}/${RUN_ID}.log"
    fi

    # Stop metrics collector
    kill "${MONITOR_PID}" 2>/dev/null || true
    # Also stop any perf/collector children
    if [ -f "${RESULTS_DIR}/.collector_pid_${RUN_ID}" ]; then
        kill "$(cat "${RESULTS_DIR}/.collector_pid_${RUN_ID}")" 2>/dev/null || true
        rm -f "${RESULTS_DIR}/.collector_pid_${RUN_ID}"
    fi
    if [ -f "${RESULTS_DIR}/.perf_pid_${RUN_ID}" ]; then
        kill "$(cat "${RESULTS_DIR}/.perf_pid_${RUN_ID}")" 2>/dev/null || true
        rm -f "${RESULTS_DIR}/.perf_pid_${RUN_ID}"
    fi

    echo "[run_all] Scenario ${RUN_ID} done."
    # Cool-down between scenarios to let resources stabilize
    sleep 5
}

# ─── Run all scenarios ────────────────────────────────────────────────────────

for SUBS in ${SUBMISSIONS_LIST}; do
    for W in ${WORKERS_LIST}; do
        run_scenario "celery" "${W}" "${SUBS}"
        run_scenario "ray"    "${W}" "${SUBS}"
    done
done

echo ""
echo "[run_all] All scenarios complete."
echo "[run_all] Generating figures..."

docker compose run --rm bench \
    python benchmarks/plot_results.py \
    --results-csv "/results/results.csv" \
    --sys-csv "/results/sys_metrics_*.csv" \
    --output-dir "/results/figures"

echo "[run_all] Figures written to ${RESULTS_DIR}/figures/"
echo "[run_all] Done."
date
