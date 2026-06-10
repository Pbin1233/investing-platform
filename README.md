# Investing Platform

A self-hosted portfolio tracking and investment analytics platform built with Python, PostgreSQL, Docker, and Streamlit.

The project started as a replacement for a large spreadsheet-based workflow and evolved into a structured system with:

* transaction tracking
* portfolio valuation
* broker cash reconciliation
* realized gain calculations
* benchmark comparison
* XIRR analytics
* withholding and yearly tax estimates
* historical market data storage
* allocation analytics
* automated maintenance jobs
* dashboard visualization

The platform is designed to be incremental and extensible. New analytics and research ideas can be added as independent modules without breaking the existing accounting layer.

---

# Core Features

## Portfolio Accounting

* Multi-broker support
* Multi-currency support
* EUR-normalized accounting
* BUY/SELL transaction ledger
* Dividend tracking
* Cash flow tracking
* Realized gain calculations using LIFO
* Portfolio snapshots

## Performance Analytics

* Portfolio XIRR
* Broker-level XIRR
* Position-level XIRR
* Benchmark comparison (currently SPY)
* Allocation analysis
* Concentration metrics
* Performance history
* Historical return analytics
* Volatility estimation
* Drawdown tracking

## Tax Estimates

The system summarizes imported tax-relevant broker data and computes yearly
estimates for:

* realized gains
* dividend withholding
* dividend tax due after withholding
* 0.2% IVAFE based on real year-end market value
* yearly broker activity

Year-end market value is calculated from positions held at 31 December and the
latest stored EUR-adjusted price on or before that date. If a held position has
no available price for that year-end, the yearly summary exposes it through
`year_end_unpriced_positions`.

---

# Architecture

## Stack

* Python 3.12+
* PostgreSQL
* SQLAlchemy
* Pandas
* Streamlit
* Docker / Docker Compose
* yfinance

## Main Components

```text
app/
├── dashboard/          # Streamlit dashboard
├── database/           # Connection helpers and migrations
├── market_data/        # Price and FX updates
├── ops/                # Maintenance and operational tooling
├── portfolio/          # Portfolio analytics
├── tests/              # Unit tests
```

---

# Dashboard

The Streamlit dashboard currently includes:

* Account Summary
* Portfolio Valuation
* Transactions
* Dividends
* Realized Gains
* Yearly Summary
* Market Analytics

---

# Automated Maintenance

The platform includes a daily maintenance pipeline:

1. Update latest market prices
2. Update historical daily prices
3. Create portfolio snapshot
4. Create PostgreSQL backup

Maintenance jobs are logged in the `job_runs` table with:

* execution status
* timestamps
* processed rows
* structured stage metadata

The daily maintenance job checks the exchanges used by active securities before
updating prices or taking a snapshot. If any configured market is still open, it
records the job as skipped so the dashboard does not mix closed-market and
live/intraday prices. With the current holdings, a practical schedule is late
evening in Europe/Rome after the US close and before the Korean market opens.

---

# Historical Market Data

Historical prices are stored in the `daily_prices` table.

The system currently supports:

* daily EUR-adjusted prices
* rolling return calculations
* volatility analytics
* drawdown analytics

This layer is intended to support future research and screening systems.

---

# Research Prototype

The dashboard includes an initial `Research` tab for idea tracking. It combines
current portfolio weights with a small demo watchlist and fields for thesis,
risk, target weight, and next action. This is intentionally a prototype: ideas
are code-defined demo rows for now, not a persistent database table and not
investment recommendations.

---

# Data Quality Checks

The platform includes internal validation utilities for:

* negative positions
* duplicate transactions
* missing FX rates
* stale market prices

These checks are intended to reduce silent accounting errors.

---

# Running Locally

## Clone Repository

```bash
git clone https://github.com/Pbin1233/investing-platform.git
cd investing-platform
```

## Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r app/requirements.txt
```

## Run Dashboard

```bash
streamlit run app/dashboard/dashboard.py
```

---

# Docker Deployment

The platform is designed to run through Docker Compose.

Typical deployment flow:

```bash
sudo docker compose up -d --build app
```

---

# Testing

Run tests with:

```bash
python -m pytest
```

---

# IBKR Statement Imports

Broker statement CSVs can be parsed without replacing existing data.

IBKR transaction statement CSVs:

```bash
python -m app.imports.import_ib_statement "test imports/ib/U19672266.TRANSACTIONS.20240528.20260604.csv"
```

DEGIRO account CSVs:

```bash
python -m app.imports.import_degiro_account "test imports/degiro/Account.csv"
```

Both commands default to a dry run. They normalize stock trades, dividends with
withholding taxes, and cash deposits/withdrawals. Unsupported broker bookkeeping
rows, such as FX translation adjustments, cash sweep transfers, and stock split
ledger rows, are reported as ignored rows.

After reviewing the dry run and applying migrations, write new rows with:

```bash
python -m app.database.run_migrations
python -m app.imports.import_ib_statement "path/to/ib_statement.csv" --apply
python -m app.imports.import_degiro_account "path/to/degiro_account.csv" --apply
```

Applied imports are tracked in `import_records` using stable source hashes, so
overlapping future IBKR exports can be imported without duplicating rows.

---

# Future Direction

Planned or partially implemented ideas include:

* research/screening engine
* S&P 500 candidate tracking
* factor analytics
* rolling correlations
* benchmark-relative ranking
* momentum analytics
* signal generation
* automated alerts
* dashboard health monitoring
* anomaly detection

The long-term goal is not only portfolio tracking, but building a structured personal investment research environment.

---

# Disclaimer

This project is for personal portfolio management and research purposes.

Nothing in this repository constitutes financial, legal, or tax advice.
