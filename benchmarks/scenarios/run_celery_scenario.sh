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

# Support both Docker Compose V2 plugin and V1 standalone
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

echo "[celery] Starting scenario: ${RUN_ID}"

# Purge broker queues so leftover tasks from previous runs don't contaminate results
echo "[celery] Purging broker queues..."
docker exec exp-redis redis-cli DEL exp-compile exp-judge > /dev/null 2>&1 || true

# Start Celery workers with the requested concurrency.
# --force-recreate ensures workers always use the current image, not a stale container.
$DC \
    -f docker-compose.yml \
    -f docker-compose.celery.yml \
    up -d \
    --force-recreate \
    --scale celery-compile-worker="${WORKERS}" \
    --scale celery-judge-worker="${WORKERS}"

# Wait for workers to be healthy
echo "[celery] Waiting for workers to be ready..."
sleep 8

# Run the benchmark driver
$DC \
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
$DC \
    -f docker-compose.yml \
    -f docker-compose.celery.yml \
    stop celery-compile-worker celery-judge-worker

echo "[celery] Scenario ${RUN_ID} complete."
