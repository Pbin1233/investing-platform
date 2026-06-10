import pandas as pd

from app.research.ideas import ideas


def test_build_research_ideas_includes_owned_and_watch_rows(monkeypatch):
    monkeypatch.setattr(
        ideas,
        "calculate_portfolio",
        lambda: pd.DataFrame(
            [
                {"ticker": "ASML", "market_value_eur": 70.0},
                {"ticker": "AVGO", "market_value_eur": 30.0},
            ]
        ),
    )

    result = ideas.build_research_ideas()

    assert {"owned", "watch"}.issubset(set(result["status"]))
    assert "gap_to_target_pct" in result.columns

    asml = result[result["ticker"] == "ASML"].iloc[0]
    assert asml["current_weight_pct"] == 70.0
    assert asml["current_value_eur"] == 70.0

    tsm = result[result["ticker"] == "TSM"].iloc[0]
    assert tsm["current_weight_pct"] == 0.0
    assert bool(tsm["demo"]) is True


def test_research_summary_counts_statuses():
    frame = pd.DataFrame(
        [
            {"status": "owned", "idea_score": 8},
            {"status": "watch", "idea_score": 6},
        ]
    )

    summary = ideas.research_summary(frame)

    assert summary["idea_count"] == 2
    assert summary["owned_count"] == 1
    assert summary["watch_count"] == 1
    assert summary["avg_score"] == 7.0
