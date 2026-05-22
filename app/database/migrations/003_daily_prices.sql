CREATE TABLE IF NOT EXISTS daily_prices (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    price_symbol TEXT NOT NULL,
    price_date DATE NOT NULL,
    close_price NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL,
    fx_rate_to_eur NUMERIC(20, 8) NOT NULL,
    close_price_eur NUMERIC(20, 8) NOT NULL,
    volume BIGINT,
    source TEXT NOT NULL DEFAULT 'yfinance',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (ticker, price_date, source)
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date
ON daily_prices (ticker, price_date DESC);
