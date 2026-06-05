CREATE TABLE IF NOT EXISTS import_records (
    import_record_id BIGSERIAL PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_hash TEXT NOT NULL UNIQUE,
    target_table TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_import_records_source_file
ON import_records (source_system, source_file);

CREATE INDEX IF NOT EXISTS idx_import_records_target
ON import_records (target_table, target_id);
