import os

import pandas as pd

from app.ops.system_health import build_system_health_rows, latest_backup_info


def test_latest_backup_info_reports_missing_directory(tmp_path):
    info = latest_backup_info(tmp_path / "missing")

    assert info["status"] == "MISSING"
    assert "not found" in info["detail"]


def test_latest_backup_info_flags_tiny_backup(tmp_path):
    backup = tmp_path / "tiny.sql.gz"
    backup.write_bytes(b"x")

    info = latest_backup_info(tmp_path, min_size_bytes=10)

    assert info["status"] == "CHECK"
    assert info["name"] == "tiny.sql.gz"
    assert "only 1 bytes" in info["detail"]


def test_latest_backup_info_uses_latest_backup_by_mtime(tmp_path):
    older = tmp_path / "older.sql.gz"
    newer = tmp_path / "newer.sql.gz"
    older.write_bytes(b"x" * 20)
    newer.write_bytes(b"x" * 20)
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    info = latest_backup_info(tmp_path, min_size_bytes=10)

    assert info["status"] == "OK"
    assert info["name"] == "newer.sql.gz"
    assert info["size_bytes"] == 20


def test_build_system_health_rows_summarizes_ok_state():
    latest_jobs = pd.DataFrame(
        [
            {
                "job_name": "daily_maintenance",
                "status": "success",
                "started_at": "2026-06-18 21:15",
                "age_hours": 12.0,
            },
            {
                "job_name": "broker_refresh_DEGIRO",
                "status": "success",
                "started_at": "2026-06-18 12:00",
                "age_hours": 21.0,
            },
            {
                "job_name": "broker_refresh_IB",
                "status": "success",
                "started_at": "2026-06-18 12:01",
                "age_hours": 21.0,
            },
            {
                "job_name": "broker_refresh_INTESA",
                "status": "success",
                "started_at": "2026-06-18 12:02",
                "age_hours": 21.0,
            },
        ]
    )
    market_health = pd.DataFrame(
        [
            {"ticker": "ASML", "status": "OK"},
            {"ticker": "NVDA", "status": "OK"},
        ]
    )
    quality_checks = {
        "negative_positions": pd.DataFrame(),
        "stale_prices": pd.DataFrame(),
    }
    backup_info = {
        "status": "OK",
        "detail": "investing.sql.gz (1000 bytes)",
    }

    result = build_system_health_rows(
        latest_jobs,
        market_health,
        quality_checks,
        backup_info,
    )

    assert set(result["status"]) == {"OK"}
    assert result[result["area"] == "Market data"].iloc[0]["detail"] == (
        "2 active securities, 0 issue rows"
    )


def test_build_system_health_rows_flags_issues():
    latest_jobs = pd.DataFrame(
        [
            {
                "job_name": "daily_maintenance",
                "status": "failed",
                "started_at": "2026-06-18 21:15",
                "age_hours": 12.0,
            }
        ]
    )
    market_health = pd.DataFrame([{"ticker": "ASML", "status": "STALE"}])
    quality_checks = {"stale_prices": pd.DataFrame([{"ticker": "ASML"}])}
    backup_info = {
        "status": "CHECK",
        "detail": "tiny.sql.gz is only 1 bytes",
    }

    result = build_system_health_rows(
        latest_jobs,
        market_health,
        quality_checks,
        backup_info,
    )

    statuses = dict(zip(result["area"], result["status"], strict=True))
    assert statuses["Daily maintenance"] == "CHECK"
    assert statuses["Market data"] == "CHECK"
    assert statuses["Data quality"] == "CHECK"
    assert statuses["broker_refresh_INTESA"] == "MISSING"
    assert statuses["Latest backup"] == "CHECK"
