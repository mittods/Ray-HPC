#!/usr/bin/env bash
# Run a single Ray scenario.
# Args: <run_id> <workers> <submissions> <seed> <results_dir>
#
# Ray uses a single head node; the number of CPU slots is set via
# RAY_NUM_CPUS environment variable passed to the driver container.
# For multi-node, additional worker nodes would be added here.

set -eu

RUN_ID="${1}"
WORKERS="${2}"
SUBMISSIONS="${3}"
SEED="${4:-42}"
RESULTS_DIR="${5:-/results}"

# Support both Docker Compose V2 plugin and V1 standalone
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

echo "[ray] Starting scenario: ${RUN_ID}"

# Start Ray head node. --force-recreate ensures the latest image is used.
$DC \
    -f docker-compose.yml \
    -f docker-compose.ray.yml \
    up -d --force-recreate ray-head

echo "[ray] Waiting for Ray head to initialize..."
sleep 10

# Run the benchmark driver with the specified CPU budget
$DC \
    -f docker-compose.yml \
    -f docker-compose.ray.yml \
    run --rm \
    -e RAY_NUM_CPUS="${WORKERS}" \
    bench \
    python benchmarks/run_ray_bench.py \
        --run-id "${RUN_ID}" \
        --submissions "${SUBMISSIONS}" \
        --workers "${WORKERS}" \
        --seed "${SEED}" \
        --output "/results/${RUN_ID}.json" \
        --csv "/results/results.csv"

# Tear down Ray head (keep infrastructure)
$DC \
    -f docker-compose.yml \
    -f docker-compose.ray.yml \
    stop ray-head

echo "[ray] Scenario ${RUN_ID} complete."
