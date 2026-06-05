from decimal import Decimal

import pytest

from app.portfolio.cost_basis import Trade, lifo_realized_gains


def test_lifo_realized_gains_adjusts_lots_for_stock_split():
    trades = [
        Trade("2024-04-19", "BUY", Decimal("5"), Decimal("770"), Decimal("2"), Decimal("0.94")),
        Trade("2024-06-10", "SPLIT", Decimal("45"), Decimal("0"), Decimal("0"), Decimal("1")),
        Trade("2024-07-25", "SELL", Decimal("50"), Decimal("108"), Decimal("2"), Decimal("0.92")),
    ]

    gains = lifo_realized_gains(trades)

    assert len(gains) == 1
    assert gains[0].quantity == Decimal("50")
    assert gains[0].cost_basis_eur == pytest.approx(Decimal("3620.88"))
