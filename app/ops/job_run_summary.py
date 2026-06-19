import json
from typing import Any

import pandas as pd


SUMMARY_COLUMNS = [
    "job_name",
    "status",
    "started_at",
    "completed_at",
    "stage",
    "detail",
]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (dict, list, tuple, set)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _compact(value: Any, max_length: int = 180) -> str:
    if _is_blank(value):
        return ""

    text = str(value).strip()
    if len(text) <= max_length:
        return text

    return f"{text[: max_length - 1]}..."


def _display_value(value: Any) -> str:
    return _compact(value, max_length=80)


def _parse_message(message: Any) -> dict[str, Any] | None:
    if _is_blank(message):
        return None

    if isinstance(message, dict):
        return message

    if not isinstance(message, str):
        return None

    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _count_detail(summary: dict[str, Any]) -> str:
    parts = []
    for key in (
        "inserted",
        "already_imported",
        "matched_existing",
        "transactions",
        "dividends",
        "cash_flows",
        "ignored",
    ):
        if key in summary:
            parts.append(f"{key.replace('_', ' ')}: {summary[key]}")

    return ", ".join(parts)


def _broker_refresh_detail(payload: dict[str, Any]) -> tuple[str, str]:
    report = payload.get("report", {})
    if not isinstance(report, dict):
        return "broker refresh", "Malformed broker refresh report"

    broker = report.get("broker") or report.get("broker_name") or "broker"
    mode = report.get("mode", "unknown")
    source_file = report.get("source_file") or report.get("requested_file") or "unknown file"
    error = payload.get("error")

    summary = (
        report.get("apply_summary")
        or report.get("pre_refresh_dry_run")
        or report.get("post_refresh_dry_run")
        or {}
    )
    counts = _count_detail(summary) if isinstance(summary, dict) else ""

    detail_parts = [f"{broker} {mode}", str(source_file)]
    if counts:
        detail_parts.append(counts)
    if report.get("backup"):
        detail_parts.append(f"backup: {report['backup']}")
    if error:
        detail_parts.append(f"error: {error}")

    return "broker refresh", _compact("; ".join(detail_parts))


def _rows_for_payload(row: pd.Series, payload: dict[str, Any]) -> list[dict[str, Any]]:
    base = {
        "job_name": row.get("job_name"),
        "status": row.get("status"),
        "started_at": _display_value(row.get("started_at")),
        "completed_at": _display_value(row.get("completed_at")),
    }

    if payload.get("kind") == "broker_refresh":
        stage, detail = _broker_refresh_detail(payload)
        return [{**base, "stage": stage, "detail": detail}]

    stages = payload.get("stages")
    if isinstance(stages, list):
        rows = []
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            rows.append(
                {
                    **base,
                    "status": stage.get("status") or base["status"],
                    "started_at": _display_value(
                        stage.get("started_at") or base["started_at"]
                    ),
                    "completed_at": _display_value(
                        stage.get("completed_at") or base["completed_at"]
                    ),
                    "stage": stage.get("stage") or "stage",
                    "detail": _compact(stage.get("message")),
                }
            )
        if rows:
            return rows

    if payload.get("status") == "skipped":
        reason = payload.get("reason", "unknown")
        blockers = payload.get("blockers")
        detail = f"Skipped: {reason}"
        if blockers:
            detail = f"{detail}; blockers: {len(blockers)}"
        return [{**base, "stage": "daily maintenance", "detail": detail}]

    return [
        {
            **base,
            "stage": "summary",
            "detail": _compact(json.dumps(payload, default=str)),
        }
    ]


def build_job_run_summary_rows(job_runs: pd.DataFrame) -> pd.DataFrame:
    if job_runs.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    rows: list[dict[str, Any]] = []

    for _, row in job_runs.iterrows():
        payload = _parse_message(row.get("message"))
        if payload:
            rows.extend(_rows_for_payload(row, payload))
            continue

        rows.append(
            {
                "job_name": row.get("job_name"),
                "status": row.get("status"),
                "started_at": _display_value(row.get("started_at")),
                "completed_at": _display_value(row.get("completed_at")),
                "stage": "summary",
                "detail": _compact(row.get("message")),
            }
        )

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
