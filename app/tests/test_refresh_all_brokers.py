import os
from pathlib import Path

from app.imports import refresh_all_brokers


def _write_csv(path: Path, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("header\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_find_latest_csv_uses_mtime_then_name(tmp_path):
    older = tmp_path / "ib" / "older.csv"
    newer_a = tmp_path / "ib" / "newer_a.csv"
    newer_b = tmp_path / "ib" / "newer_b.csv"
    ignored = tmp_path / "ib" / "notes.txt"

    _write_csv(older, 100)
    _write_csv(newer_a, 200)
    _write_csv(newer_b, 200)
    ignored.write_text("ignored", encoding="utf-8")

    assert refresh_all_brokers.find_latest_csv(tmp_path, "IB") == newer_b


def test_refresh_all_brokers_runs_each_latest_csv(monkeypatch, tmp_path):
    ib_file = tmp_path / "ib" / "ib.csv"
    degiro_file = tmp_path / "degiro" / "degiro.csv"
    _write_csv(ib_file, 100)
    _write_csv(degiro_file, 101)

    calls = []

    def fake_refresh_broker(broker, path, apply, yes, skip_backup):
        calls.append((broker, path, apply, yes, skip_backup))
        return {
            "broker": broker,
            "source_file": path.name,
            "mode": "apply" if apply else "dry-run",
        }

    monkeypatch.setattr(
        refresh_all_brokers,
        "refresh_broker",
        fake_refresh_broker,
    )

    report = refresh_all_brokers.refresh_all_brokers(
        import_root=tmp_path,
        apply=True,
        yes=True,
        skip_backup=True,
    )

    assert report["status"] == "success"
    assert report["mode"] == "apply"
    assert calls == [
        ("DEGIRO", degiro_file, True, True, True),
        ("IB", ib_file, True, True, True),
    ]
    assert [broker["status"] for broker in report["brokers"]] == [
        "success",
        "success",
    ]


def test_refresh_all_brokers_reports_missing_csv_and_continues(monkeypatch, tmp_path):
    ib_file = tmp_path / "ib" / "ib.csv"
    _write_csv(ib_file, 100)

    calls = []

    def fake_refresh_broker(broker, path, apply, yes, skip_backup):
        calls.append((broker, path))
        return {"broker": broker, "source_file": path.name}

    monkeypatch.setattr(
        refresh_all_brokers,
        "refresh_broker",
        fake_refresh_broker,
    )

    report = refresh_all_brokers.refresh_all_brokers(import_root=tmp_path)

    assert report["status"] == "failed"
    assert calls == [("IB", ib_file)]
    failures = [
        broker
        for broker in report["brokers"]
        if broker["status"] == "failed"
    ]
    assert failures[0]["broker"] == "DEGIRO"
    assert "No CSV files found" in failures[0]["error"]
