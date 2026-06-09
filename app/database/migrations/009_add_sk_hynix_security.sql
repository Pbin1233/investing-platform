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
    '000660.KS',
    'SK hynix Inc',
    '000660.KS',
    'KRW',
    'KRX',
    'KR',
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
