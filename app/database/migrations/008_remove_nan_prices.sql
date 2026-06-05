DELETE FROM daily_prices
WHERE close_price::TEXT = 'NaN'
   OR close_price_eur::TEXT = 'NaN'
   OR fx_rate_to_eur::TEXT = 'NaN';

DELETE FROM prices
WHERE close_price::TEXT = 'NaN'
   OR fx_rate_to_eur::TEXT = 'NaN'
   OR (close_price * fx_rate_to_eur)::TEXT = 'NaN';
