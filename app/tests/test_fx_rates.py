import pandas as pd

from app.market_data import update_prices


class FakeTicker:
    def __init__(self, symbol, prices):
        self.symbol = symbol
        self.prices = prices

    def history(self, period="1d"):
        price = self.prices[self.symbol]
        return pd.DataFrame({"Close": [price]})


def test_fx_to_eur_supports_krw_cross_rate(monkeypatch):
    prices = {
        "USDKRW=X": 1350.0,
        "EURUSD=X": 1.08,
    }

    monkeypatch.setattr(
        update_prices.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, prices),
    )

    assert update_prices.fx_to_eur("KRW") == 1 / (1350.0 * 1.08)


def test_fx_to_eur_keeps_usd_inverse_eurusd(monkeypatch):
    prices = {"EURUSD=X": 1.08}

    monkeypatch.setattr(
        update_prices.yf,
        "Ticker",
        lambda symbol: FakeTicker(symbol, prices),
    )

    assert update_prices.fx_to_eur("USD") == 1 / 1.08
