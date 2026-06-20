CREATE TABLE IF NOT EXISTS broker_position_valuations (
    valuation_id BIGSERIAL PRIMARY KEY,
    broker_name TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_file TEXT NOT NULL,
    valuation_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    asset_name TEXT,
    quantity NUMERIC(20, 8) NOT NULL,
    market_value_eur NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (broker_name, source_system, source_file, valuation_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_broker_position_valuations_latest
ON broker_position_valuations (broker_name, ticker, valuation_date DESC, valuation_id DESC);
