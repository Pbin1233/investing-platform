ALTER TABLE transactions
DROP CONSTRAINT IF EXISTS transactions_action_check;

ALTER TABLE transactions
ADD CONSTRAINT transactions_action_check
CHECK (action IN ('BUY', 'SELL', 'SPLIT'));

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
