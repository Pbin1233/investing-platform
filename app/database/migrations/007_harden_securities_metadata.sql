ALTER TABLE securities
ADD COLUMN IF NOT EXISTS asset_name TEXT;

ALTER TABLE securities
ADD COLUMN IF NOT EXISTS country TEXT;

ALTER TABLE securities
ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE securities
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

INSERT INTO securities (
    ticker,
    asset_name,
    price_symbol,
    quote_currency,
    exchange,
    country,
    active
)
VALUES (
    'QRVO',
    'Qorvo Inc',
    'QRVO',
    'USD',
    'NASDAQ',
    'US',
    TRUE
)
ON CONFLICT (ticker)
DO UPDATE SET
    asset_name = COALESCE(securities.asset_name, EXCLUDED.asset_name),
    price_symbol = EXCLUDED.price_symbol,
    quote_currency = EXCLUDED.quote_currency,
    exchange = COALESCE(securities.exchange, EXCLUDED.exchange),
    country = COALESCE(securities.country, EXCLUDED.country),
    active = TRUE;
