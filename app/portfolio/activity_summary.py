from datetime import date
from typing import Any

import pandas as pd


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="mixed")


def _date_label(value: Any) -> str:
    if pd.isna(value):
        return "n/a"

    if hasattr(value, "date"):
        value = value.date()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def _with_month(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    df = df.copy()
    dates = _to_datetime(df[date_column])
    df = df[dates.notna()].copy()
    df["month"] = dates[dates.notna()].dt.to_period("M").astype(str)
    return df


def build_activity_snapshot(
    transactions: pd.DataFrame,
    cash_flows: pd.DataFrame,
    import_records: pd.DataFrame,
) -> dict[str, str | int | float]:
    latest_trade = "n/a"
    trade_count = 0
    if not transactions.empty and "trade_date" in transactions.columns:
        trade_dates = _to_datetime(transactions["trade_date"])
        latest_trade = _date_label(trade_dates.max())
        trade_count = len(transactions)

    net_flow_eur = 0.0
    latest_flow = "n/a"
    if not cash_flows.empty:
        if "amount_eur" in cash_flows.columns:
            net_flow_eur = float(pd.to_numeric(cash_flows["amount_eur"]).sum())
        if "flow_date" in cash_flows.columns:
            latest_flow = _date_label(_to_datetime(cash_flows["flow_date"]).max())

    latest_import = "n/a"
    latest_import_file = "n/a"
    if not import_records.empty and "imported_at" in import_records.columns:
        records = import_records.copy()
        records["_imported_at"] = _to_datetime(records["imported_at"])
        records = records.sort_values("_imported_at", ascending=False)
        latest = records.iloc[0]
        latest_import = _date_label(latest["_imported_at"])
        latest_import_file = str(latest.get("source_file") or "n/a")

    return {
        "trade_count": trade_count,
        "latest_trade": latest_trade,
        "net_flow_eur": net_flow_eur,
        "latest_flow": latest_flow,
        "latest_import": latest_import,
        "latest_import_file": latest_import_file,
    }


def build_monthly_activity(
    transactions: pd.DataFrame,
    cash_flows: pd.DataFrame,
    import_records: pd.DataFrame,
    limit: int = 12,
) -> pd.DataFrame:
    frames = []

    if not transactions.empty and "trade_date" in transactions.columns:
        trades = _with_month(transactions, "trade_date")
        if not trades.empty:
            grouped = trades.groupby("month").agg(
                transactions=("trade_date", "size"),
                buys=("action", lambda values: int((values == "BUY").sum())),
                sells=("action", lambda values: int((values == "SELL").sum())),
                splits=("action", lambda values: int((values == "SPLIT").sum())),
            )
            frames.append(grouped)

    if not cash_flows.empty and "flow_date" in cash_flows.columns:
        flows = _with_month(cash_flows, "flow_date")
        if not flows.empty:
            if "amount_eur" not in flows.columns:
                flows["amount_eur"] = 0.0
            grouped = flows.groupby("month").agg(
                cash_flows=("flow_date", "size"),
                net_flow_eur=("amount_eur", "sum"),
            )
            frames.append(grouped)

    if not import_records.empty and "imported_at" in import_records.columns:
        imports = _with_month(import_records, "imported_at")
        if not imports.empty:
            grouped = imports.groupby("month").agg(
                imported_rows=("imported_at", "size"),
                import_files=("source_file", pd.Series.nunique),
            )
            frames.append(grouped)

    if not frames:
        return pd.DataFrame(
            columns=[
                "month",
                "transactions",
                "buys",
                "sells",
                "splits",
                "cash_flows",
                "net_flow_eur",
                "imported_rows",
                "import_files",
            ]
        )

    monthly = pd.concat(frames, axis=1).fillna(0).reset_index()
    numeric_columns = [
        "transactions",
        "buys",
        "sells",
        "splits",
        "cash_flows",
        "imported_rows",
        "import_files",
    ]
    for column in numeric_columns:
        if column in monthly.columns:
            monthly[column] = monthly[column].astype(int)

    if "net_flow_eur" in monthly.columns:
        monthly["net_flow_eur"] = pd.to_numeric(monthly["net_flow_eur"])

    return monthly.sort_values("month", ascending=False).head(limit)
