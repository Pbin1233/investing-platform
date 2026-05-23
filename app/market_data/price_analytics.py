import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


def load_daily_prices() -> pd.DataFrame:
    engine = get_engine()

    df = pd.read_sql(
        text("""
            SELECT
                ticker,
                price_date,
                close_price_eur,
                volume
            FROM daily_prices
            ORDER BY ticker, price_date
        """),
        engine,
    )

    if df.empty:
        return df

    df["price_date"] = pd.to_datetime(df["price_date"])
    df["close_price_eur"] = pd.to_numeric(
        df["close_price_eur"],
        errors="coerce",
    )

    return df.dropna(subset=["close_price_eur"])


def _return_over_days(group: pd.DataFrame, days: int) -> float | None:
    if group.empty:
        return None

    latest_date = group["price_date"].max()
    target_date = latest_date - pd.Timedelta(days=days)

    past = group[group["price_date"] <= target_date]

    if past.empty:
        return None

    latest_price = group.loc[
        group["price_date"] == latest_date,
        "close_price_eur",
    ].iloc[-1]

    past_price = past.iloc[-1]["close_price_eur"]

    if past_price == 0:
        return None

    return (latest_price / past_price - 1) * 100


def _max_drawdown_pct(group: pd.DataFrame) -> float | None:
    if group.empty:
        return None

    prices = group["close_price_eur"]

    running_peak = prices.cummax()
    drawdown = (prices - running_peak) / running_peak * 100

    return float(drawdown.min())


def calculate_price_analytics() -> pd.DataFrame:
    prices = load_daily_prices()

    if prices.empty:
        return pd.DataFrame()

    rows = []

    for ticker, group in prices.groupby("ticker"):
        group = group.sort_values("price_date").copy()
        group["daily_return"] = group["close_price_eur"].pct_change()

        latest = group.iloc[-1]

        volatility_annualized = (
            group["daily_return"].std() * (252 ** 0.5) * 100
            if group["daily_return"].notna().sum() > 2
            else None
        )

        rows.append(
            {
                "ticker": ticker,
                "latest_date": latest["price_date"].date(),
                "latest_price_eur": float(latest["close_price_eur"]),
                "return_1d_pct": _return_over_days(group, 1),
                "return_5d_pct": _return_over_days(group, 5),
                "return_1m_pct": _return_over_days(group, 30),
                "return_3m_pct": _return_over_days(group, 90),
                "return_1y_pct": _return_over_days(group, 365),
                "volatility_annualized_pct": volatility_annualized,
                "max_drawdown_pct": _max_drawdown_pct(group),
                "observations": len(group),
            }
        )

    return pd.DataFrame(rows).sort_values("ticker")


def main():
    df = calculate_price_analytics()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
