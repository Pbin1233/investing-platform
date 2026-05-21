CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    rows_processed INTEGER,
    message TEXT,

    CONSTRAINT job_runs_status_check
        CHECK (status IN ('started', 'success', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_name_started_at
    ON job_runs (job_name, started_at DESC);
