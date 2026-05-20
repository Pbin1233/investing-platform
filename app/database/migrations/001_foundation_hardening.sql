CREATE TABLE IF NOT EXISTS securities (
    ticker TEXT PRIMARY KEY,
    asset_name TEXT,
    price_symbol TEXT NOT NULL,
    quote_currency TEXT NOT NULL DEFAULT 'EUR',
    exchange TEXT,
    country TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    broker_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    market_value_eur NUMERIC(20, 8),
    invested_eur NUMERIC(20, 8),
    unrealized_pl_eur NUMERIC(20, 8),
    unrealized_pl_pct NUMERIC(20, 8),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, broker_name, ticker)
);

CREATE INDEX IF NOT EXISTS idx_transactions_broker_ticker_date
ON transactions (broker_name, ticker, trade_date, transaction_id);

CREATE INDEX IF NOT EXISTS idx_transactions_ticker
ON transactions (ticker);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
ON prices (ticker, price_date DESC);

CREATE INDEX IF NOT EXISTS idx_dividends_broker_date
ON dividends (broker_name, payment_date);

CREATE INDEX IF NOT EXISTS idx_cash_flows_broker_date
ON cash_flows (broker_name, flow_date);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date
ON portfolio_snapshots (snapshot_date);
