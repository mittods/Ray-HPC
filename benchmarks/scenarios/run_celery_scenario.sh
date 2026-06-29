#!/usr/bin/env bash
# Run a single Celery scenario.
# Args: <run_id> <workers> <submissions> <seed> <results_dir>
#
# Scales the Celery compile and judge worker pools to <workers> each.

set -eu

RUN_ID="${1}"
WORKERS="${2}"
SUBMISSIONS="${3}"
SEED="${4:-42}"
RESULTS_DIR="${5:-/results}"

echo "[celery] Starting scenario: ${RUN_ID}"

# Start Celery workers with the requested concurrency
docker compose \
    -f docker-compose.yml \
    -f docker-compose.celery.yml \
    up -d \
    --scale celery-compile-worker="${WORKERS}" \
    --scale celery-judge-worker="${WORKERS}"

# Wait for workers to be healthy
echo "[celery] Waiting for workers to be ready..."
sleep 8

# Run the benchmark driver
docker compose \
    -f docker-compose.yml \
    -f docker-compose.celery.yml \
    run --rm bench \
    python benchmarks/run_celery_bench.py \
        --run-id "${RUN_ID}" \
        --submissions "${SUBMISSIONS}" \
        --workers "${WORKERS}" \
        --seed "${SEED}" \
        --output "/results/${RUN_ID}.json" \
        --csv "/results/results.csv"

# Tear down workers (keep infrastructure)
docker compose \
    -f docker-compose.yml \
    -f docker-compose.celery.yml \
    stop celery-compile-worker celery-judge-worker

echo "[celery] Scenario ${RUN_ID} complete."
