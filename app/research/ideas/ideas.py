from dataclasses import dataclass

import pandas as pd

from app.portfolio.portfolio_value import calculate_portfolio


@dataclass(frozen=True)
class Idea:
    ticker: str
    company: str
    status: str
    theme: str
    region: str
    currency: str
    idea_score: int
    valuation_note: str
    quality_note: str
    risk_note: str
    target_weight_pct: float
    next_action: str
    demo: bool = True


DEMO_IDEAS = [
    Idea(
        ticker="ASML",
        company="ASML Holding",
        status="owned",
        theme="Semiconductor equipment",
        region="Europe",
        currency="EUR",
        idea_score=8,
        valuation_note="Premium multiple; review add points only on weakness.",
        quality_note="Dominant lithography franchise with high switching costs.",
        risk_note="Cyclical capex and China export restrictions.",
        target_weight_pct=28.0,
        next_action="Hold and review concentration.",
    ),
    Idea(
        ticker="AVGO",
        company="Broadcom",
        status="owned",
        theme="AI infrastructure and dividend growth",
        region="United States",
        currency="USD",
        idea_score=8,
        valuation_note="Check whether AI growth is already fully priced.",
        quality_note="Strong cash generation and shareholder returns.",
        risk_note="Integration risk and high expectations.",
        target_weight_pct=20.0,
        next_action="Hold; add only if weight drifts below target.",
    ),
    Idea(
        ticker="NVDA",
        company="NVIDIA",
        status="owned",
        theme="Accelerated computing",
        region="United States",
        currency="USD",
        idea_score=7,
        valuation_note="Very valuation-sensitive; size position deliberately.",
        quality_note="Best-in-class AI accelerator ecosystem.",
        risk_note="Margin normalization and hyperscaler capex digestion.",
        target_weight_pct=12.0,
        next_action="Watch valuation and position size.",
    ),
    Idea(
        ticker="000660.KS",
        company="SK hynix",
        status="owned",
        theme="Memory and HBM",
        region="South Korea",
        currency="KRW",
        idea_score=7,
        valuation_note="Cyclical memory valuation; compare to HBM cycle earnings.",
        quality_note="Strong HBM exposure and AI memory relevance.",
        risk_note="Memory cycle, Korea FX, and customer concentration.",
        target_weight_pct=8.0,
        next_action="Track HBM share and cycle indicators.",
    ),
    Idea(
        ticker="TSM",
        company="Taiwan Semiconductor",
        status="watch",
        theme="Semiconductor foundry",
        region="Taiwan",
        currency="USD",
        idea_score=8,
        valuation_note="Compare ADR valuation against existing semicap exposure.",
        quality_note="Foundry scale leader with advanced-node edge.",
        risk_note="Taiwan geopolitical risk and customer concentration.",
        target_weight_pct=0.0,
        next_action="Research as diversification candidate, not automatic buy.",
    ),
    Idea(
        ticker="LRCX",
        company="Lam Research",
        status="watch",
        theme="Semiconductor equipment",
        region="United States",
        currency="USD",
        idea_score=6,
        valuation_note="Needs comparison against ASML and existing equipment weight.",
        quality_note="Strong etch/deposition exposure.",
        risk_note="Adds more semicap cyclicality.",
        target_weight_pct=0.0,
        next_action="Keep on watchlist; avoid duplicate exposure unless thesis is distinct.",
    ),
    Idea(
        ticker="MSFT",
        company="Microsoft",
        status="watch",
        theme="Cloud and AI platform",
        region="United States",
        currency="USD",
        idea_score=7,
        valuation_note="Quality premium; better as benchmark-quality comparison.",
        quality_note="Durable software, cloud, and AI distribution.",
        risk_note="Multiple compression and capex intensity.",
        target_weight_pct=0.0,
        next_action="Use as non-semiconductor watchlist anchor.",
    ),
]


def demo_ideas() -> pd.DataFrame:
    return pd.DataFrame([idea.__dict__ for idea in DEMO_IDEAS])


def current_weights() -> pd.DataFrame:
    portfolio = calculate_portfolio()

    if portfolio.empty:
        return pd.DataFrame(columns=["ticker", "current_weight_pct", "current_value_eur"])

    by_ticker = (
        portfolio.groupby("ticker", as_index=False)["market_value_eur"]
        .sum()
        .rename(columns={"market_value_eur": "current_value_eur"})
    )
    total_value = by_ticker["current_value_eur"].sum()
    by_ticker["current_weight_pct"] = (
        by_ticker["current_value_eur"] / total_value * 100
        if total_value
        else 0.0
    )

    return by_ticker


def build_research_ideas() -> pd.DataFrame:
    ideas = demo_ideas()
    weights = current_weights()

    research = ideas.merge(weights, on="ticker", how="left")
    research["current_value_eur"] = research["current_value_eur"].fillna(0.0)
    research["current_weight_pct"] = research["current_weight_pct"].fillna(0.0)
    research["gap_to_target_pct"] = (
        research["target_weight_pct"] - research["current_weight_pct"]
    )
    research["last_reviewed"] = None

    ordered_columns = [
        "ticker",
        "company",
        "status",
        "theme",
        "region",
        "currency",
        "idea_score",
        "current_value_eur",
        "current_weight_pct",
        "target_weight_pct",
        "gap_to_target_pct",
        "valuation_note",
        "quality_note",
        "risk_note",
        "next_action",
        "last_reviewed",
        "demo",
    ]

    return research[ordered_columns].sort_values(
        ["status", "idea_score", "current_weight_pct"],
        ascending=[True, False, False],
    )


def research_summary(ideas: pd.DataFrame) -> dict:
    if ideas.empty:
        return {
            "idea_count": 0,
            "owned_count": 0,
            "watch_count": 0,
            "avg_score": None,
        }

    return {
        "idea_count": len(ideas),
        "owned_count": int((ideas["status"] == "owned").sum()),
        "watch_count": int((ideas["status"] == "watch").sum()),
        "avg_score": float(ideas["idea_score"].mean()),
    }


def main():
    print(build_research_ideas().to_string(index=False))


if __name__ == "__main__":
    main()
