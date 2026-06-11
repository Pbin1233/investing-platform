from types import SimpleNamespace

import pytest

from app.imports import refresh_broker


def _parsed():
    return SimpleNamespace(source_file="statement.csv")


def _summary(inserted=0, matched_existing=0, already_imported=0):
    return {
        "source_file": "statement.csv",
        "transactions": 1,
        "dividends": 0,
        "cash_flows": 0,
        "ignored": 0,
        "already_imported": already_imported,
        "matched_existing": matched_existing,
        "inserted": inserted,
    }


def test_refresh_broker_dry_run_does_not_delete_or_apply(monkeypatch):
    calls = []

    monkeypatch.setattr(refresh_broker, "parse_broker_file", lambda broker, path: _parsed())
    monkeypatch.setattr(
        refresh_broker,
        "import_statement",
        lambda parsed, apply, source_system: calls.append(apply) or _summary(inserted=1),
    )
    monkeypatch.setattr(
        refresh_broker,
        "delete_broker_rows",
        lambda broker_name, source_system: pytest.fail("delete should not run"),
    )

    report = refresh_broker.refresh_broker("IB", "statement.csv")

    assert report["mode"] == "dry-run"
    assert calls == [False]
    assert report["pre_refresh_dry_run"]["inserted"] == 1


def test_refresh_broker_apply_requires_yes(monkeypatch):
    monkeypatch.setattr(refresh_broker, "parse_broker_file", lambda broker, path: _parsed())
    monkeypatch.setattr(
        refresh_broker,
        "import_statement",
        lambda parsed, apply, source_system: _summary(inserted=1),
    )

    with pytest.raises(refresh_broker.RefreshError, match="--apply requires --yes"):
        refresh_broker.refresh_broker("IB", "statement.csv", apply=True)


def test_refresh_broker_apply_runs_backup_delete_import_and_checks(monkeypatch):
    calls = []

    def fake_import(parsed, apply, source_system):
        calls.append(("import", apply, source_system))
        return _summary(
            inserted=1 if apply else 0,
            already_imported=1 if not apply and len(calls) > 1 else 0,
        )

    monkeypatch.setattr(refresh_broker, "parse_broker_file", lambda broker, path: _parsed())
    monkeypatch.setattr(refresh_broker, "import_statement", fake_import)
    monkeypatch.setattr(refresh_broker, "run_backup", lambda: "Backup created: test.sql.gz")
    monkeypatch.setattr(
        refresh_broker,
        "delete_broker_rows",
        lambda broker_name, source_system: {
            "import_records": 1,
            "transactions": 1,
            "dividends": 0,
            "cash_flows": 0,
        },
    )
    monkeypatch.setattr(
        refresh_broker,
        "data_quality_summary",
        lambda: {"negative_positions": {"status": "ok", "rows": 0}},
    )

    report = refresh_broker.refresh_broker(
        "IB",
        "statement.csv",
        apply=True,
        yes=True,
    )

    assert report["backup"] == "Backup created: test.sql.gz"
    assert report["deleted"]["transactions"] == 1
    assert report["apply_summary"]["inserted"] == 1
    assert report["post_refresh_dry_run"]["inserted"] == 0
    assert calls == [
        ("import", False, "IBKR"),
        ("import", True, "IBKR"),
        ("import", False, "IBKR"),
    ]
