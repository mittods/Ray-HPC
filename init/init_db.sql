-- Experiment database initialization.
-- This script runs on first PostgreSQL startup (via docker-entrypoint-initdb.d).
-- Tables are created by SQLAlchemy (common/database.py → create_tables()),
-- but this script ensures extensions and permissions are in place.

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Grant full privileges to the dijudge user
GRANT ALL PRIVILEGES ON DATABASE dijudge_exp TO dijudge;

-- Create the experiment_submissions table explicitly as a fallback,
-- in case SQLAlchemy's create_tables() is not called before the first query.
CREATE TABLE IF NOT EXISTS experiment_submissions (
    id                  VARCHAR(36) PRIMARY KEY,
    run_id              VARCHAR(100) NOT NULL,
    framework           VARCHAR(20)  NOT NULL,
    num_workers         INTEGER      NOT NULL,
    status              VARCHAR(50)  NOT NULL DEFAULT 'queued',
    queued_at           TIMESTAMPTZ  DEFAULT NOW(),
    compile_started_at  TIMESTAMPTZ,
    compile_finished_at TIMESTAMPTZ,
    judge_started_at    TIMESTAMPTZ,
    judge_finished_at   TIMESTAMPTZ,
    verdict             VARCHAR(50),
    queue_time_ms       INTEGER,
    compile_time_ms     INTEGER,
    judge_time_ms       INTEGER,
    total_time_ms       INTEGER
);

CREATE INDEX IF NOT EXISTS idx_exp_sub_run_id   ON experiment_submissions(run_id);
CREATE INDEX IF NOT EXISTS idx_exp_sub_status   ON experiment_submissions(status);
CREATE INDEX IF NOT EXISTS idx_exp_sub_framework ON experiment_submissions(framework);
