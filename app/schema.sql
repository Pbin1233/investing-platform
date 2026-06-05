CREATE TABLE IF NOT EXISTS brokers (
    broker_id SERIAL PRIMARY KEY,
    broker_name TEXT NOT NULL UNIQUE,
    base_currency TEXT NOT NULL DEFAULT 'EUR',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    broker_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    asset_name TEXT,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'SPLIT')),
    quantity NUMERIC(20, 8) NOT NULL CHECK (quantity > 0),
    price NUMERIC(20, 8) NOT NULL CHECK (price >= 0),
    fees NUMERIC(20, 8) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR',
    fx_rate_to_eur NUMERIC(20, 8) NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dividends (
    dividend_id SERIAL PRIMARY KEY,
    payment_date DATE NOT NULL,
    broker_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    gross_amount NUMERIC(20, 8) NOT NULL,
    withholding_tax NUMERIC(20, 8) NOT NULL DEFAULT 0,
    net_amount NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    fx_rate_to_eur NUMERIC(20, 8) NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cash_flows (
    cash_flow_id SERIAL PRIMARY KEY,
    flow_date DATE NOT NULL,
    broker_name TEXT NOT NULL,
    flow_type TEXT NOT NULL CHECK (flow_type IN ('DEPOSIT', 'WITHDRAWAL', 'INTEREST', 'FEE', 'TAX')),
    amount NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    fx_rate_to_eur NUMERIC(20, 8) NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prices (
    price_id SERIAL PRIMARY KEY,
    price_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    close_price NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    fx_rate_to_eur NUMERIC(20, 8) NOT NULL DEFAULT 1,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (price_date, ticker, source)
);

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

CREATE TABLE IF NOT EXISTS import_records (
    import_record_id BIGSERIAL PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_hash TEXT NOT NULL UNIQUE,
    target_table TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW v_positions AS
SELECT
    broker_name,
    ticker,
    SUM(
        CASE
            WHEN action = 'BUY' THEN quantity
            WHEN action = 'SELL' THEN -quantity
            WHEN action = 'SPLIT' THEN quantity
        END
    ) AS quantity
FROM transactions
GROUP BY broker_name, ticker
HAVING SUM(
        CASE
            WHEN action = 'BUY' THEN quantity
            WHEN action = 'SELL' THEN -quantity
            WHEN action = 'SPLIT' THEN quantity
        END
    ) <> 0;

CREATE OR REPLACE VIEW v_trade_values AS
SELECT
    *,
    quantity * price AS gross_value,
    CASE
        WHEN action = 'BUY' THEN quantity * price + fees
        WHEN action = 'SELL' THEN quantity * price - fees
        WHEN action = 'SPLIT' THEN 0
    END AS trade_value_native,
    CASE
        WHEN action = 'BUY' THEN (quantity * price + fees) * fx_rate_to_eur
        WHEN action = 'SELL' THEN (quantity * price - fees) * fx_rate_to_eur
        WHEN action = 'SPLIT' THEN 0
    END AS trade_value_eur
FROM transactions;

CREATE OR REPLACE VIEW v_dividends_eur AS
SELECT
    *,
    gross_amount * fx_rate_to_eur AS gross_amount_eur,
    withholding_tax * fx_rate_to_eur AS withholding_tax_eur,
    net_amount * fx_rate_to_eur AS net_amount_eur
FROM dividends;

CREATE OR REPLACE VIEW v_cash_flows_eur AS
SELECT
    *,
    amount * fx_rate_to_eur AS amount_eur
FROM cash_flows;


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

CREATE INDEX IF NOT EXISTS idx_import_records_source_file
ON import_records (source_system, source_file);

CREATE INDEX IF NOT EXISTS idx_import_records_target
ON import_records (target_table, target_id);
