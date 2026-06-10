from datetime import date

import pandas as pd

from app.portfolio import benchmark


def test_fetch_close_on_or_before_ignores_nan_latest_close(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, start, end, auto_adjust):
            return pd.DataFrame(
                {"Close": [500.0, float("nan")]},
                index=pd.to_datetime(["2026-06-09", "2026-06-10"]),
            )

    monkeypatch.setattr(benchmark.yf, "Ticker", FakeTicker)

    close = benchmark.fetch_close_on_or_before("SPY", date(2026, 6, 10))

    assert close == 500.0
