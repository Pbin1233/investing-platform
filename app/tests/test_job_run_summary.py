import json

import pandas as pd

from app.ops.job_run_summary import build_job_run_summary_rows


def test_build_job_run_summary_rows_expands_daily_maintenance_stages():
    message = json.dumps(
        {
            "stages": [
                {
                    "stage": "update_prices",
                    "status": "success",
                    "started_at": "2026-06-18T20:00:00+00:00",
                    "completed_at": "2026-06-18T20:01:00+00:00",
                    "message": "Market prices updated",
                },
                {
                    "stage": "data_quality",
                    "status": "success",
                    "message": "All data quality checks passed",
                },
            ]
        }
    )
    job_runs = pd.DataFrame(
        [
            {
                "job_name": "daily_maintenance",
                "status": "success",
                "started_at": "2026-06-18 20:00",
                "completed_at": "2026-06-18 20:05",
                "message": message,
            }
        ]
    )

    result = build_job_run_summary_rows(job_runs)

    assert list(result["stage"]) == ["update_prices", "data_quality"]
    assert list(result["status"]) == ["success", "success"]
    assert result.iloc[0]["detail"] == "Market prices updated"
    assert result.iloc[1]["detail"] == "All data quality checks passed"


def test_build_job_run_summary_rows_summarizes_broker_refresh():
    message = json.dumps(
        {
            "kind": "broker_refresh",
            "report": {
                "broker": "IB",
                "mode": "dry-run",
                "source_file": "ib.csv",
                "pre_refresh_dry_run": {
                    "transactions": 4,
                    "dividends": 1,
                    "cash_flows": 2,
                    "ignored": 3,
                    "already_imported": 7,
                    "matched_existing": 8,
                    "inserted": 0,
                },
            },
        }
    )
    job_runs = pd.DataFrame(
        [
            {
                "job_name": "broker_refresh_IB",
                "status": "success",
                "started_at": "2026-06-18 20:00",
                "completed_at": "2026-06-18 20:01",
                "message": message,
            }
        ]
    )

    result = build_job_run_summary_rows(job_runs)

    assert len(result) == 1
    assert result.iloc[0]["stage"] == "broker refresh"
    assert "IB dry-run" in result.iloc[0]["detail"]
    assert "inserted: 0" in result.iloc[0]["detail"]
    assert "already imported: 7" in result.iloc[0]["detail"]


def test_build_job_run_summary_rows_handles_plain_text_message():
    job_runs = pd.DataFrame(
        [
            {
                "job_name": "snapshot_portfolio",
                "status": "success",
                "started_at": "2026-06-18 20:00",
                "completed_at": "2026-06-18 20:01",
                "message": "Snapshot saved for 2026-06-18",
            }
        ]
    )

    result = build_job_run_summary_rows(job_runs)

    assert result.iloc[0]["stage"] == "summary"
    assert result.iloc[0]["detail"] == "Snapshot saved for 2026-06-18"


def test_build_job_run_summary_rows_handles_malformed_json():
    job_runs = pd.DataFrame(
        [
            {
                "job_name": "manual_test",
                "status": "failed",
                "started_at": "2026-06-18 20:00",
                "completed_at": "2026-06-18 20:01",
                "message": '{"not valid"',
            }
        ]
    )

    result = build_job_run_summary_rows(job_runs)

    assert result.iloc[0]["stage"] == "summary"
    assert result.iloc[0]["detail"] == '{"not valid"'


def test_build_job_run_summary_rows_summarizes_market_open_skip():
    message = json.dumps(
        {
            "status": "skipped",
            "reason": "market_open",
            "blockers": [{"ticker": "AAPL"}, {"ticker": "SK Hynix"}],
        }
    )
    job_runs = pd.DataFrame(
        [
            {
                "job_name": "daily_maintenance",
                "status": "success",
                "started_at": "2026-06-18 20:00",
                "completed_at": "2026-06-18 20:01",
                "message": message,
            }
        ]
    )

    result = build_job_run_summary_rows(job_runs)

    assert result.iloc[0]["stage"] == "daily maintenance"
    assert result.iloc[0]["detail"] == "Skipped: market_open; blockers: 2"
