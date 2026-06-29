"""Experiment configuration loaded from environment variables."""
from __future__ import annotations
import os

# Database (PostgreSQL for tracking submission lifecycle)
DATABASE_URL: str = os.getenv(
    "EXP_DATABASE_URL",
    "postgresql+asyncpg://dijudge:dijudge@localhost:5433/dijudge_exp",
)

# Redis (Celery broker; unused by Ray but kept for fair infra parity)
REDIS_URL: str = os.getenv("EXP_REDIS_URL", "redis://localhost:6380/0")

# Execution mode: "simulated" or "docker"
# simulated: time.sleep simulates compile/run latency (no Docker needed)
# docker:    uses the real dijudge-sandbox Docker image
EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "simulated")

# Docker sandbox image (only used when EXECUTION_MODE=docker)
SANDBOX_IMAGE: str = os.getenv("SANDBOX_IMAGE", "dijudge-sandbox:latest")

# Simulated execution latencies (milliseconds)
COMPILE_MIN_MS: int = int(os.getenv("COMPILE_MIN_MS", "500"))
COMPILE_MAX_MS: int = int(os.getenv("COMPILE_MAX_MS", "2000"))
JUDGE_MIN_MS: int = int(os.getenv("JUDGE_MIN_MS", "100"))
JUDGE_MAX_MS: int = int(os.getenv("JUDGE_MAX_MS", "500"))

# Number of test cases per synthetic problem
TESTCASES_PER_PROBLEM: int = int(os.getenv("TESTCASES_PER_PROBLEM", "10"))

# Number of synthetic problems in the workload pool
PROBLEM_POOL_SIZE: int = int(os.getenv("PROBLEM_POOL_SIZE", "5"))

# Artifact storage root (shared volume between workers)
ARTIFACT_ROOT: str = os.getenv("ARTIFACT_ROOT", "/tmp/exp_artifacts")

# Ray cluster address (auto for local; address for multi-node)
RAY_ADDRESS: str = os.getenv("RAY_ADDRESS", "auto")

# Number of CPUs to give Ray (0 = detect automatically)
RAY_NUM_CPUS: int = int(os.getenv("RAY_NUM_CPUS", "0"))

# Results output directory
RESULTS_DIR: str = os.getenv("RESULTS_DIR", "/results")
