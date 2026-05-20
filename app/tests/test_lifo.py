from decimal import Decimal

from app.portfolio.cost_basis import Trade, lifo_realized_gains


def test_lifo_realized_gains_uses_latest_lot_first():
    trades = [
        Trade("2024-01-10", "BUY", Decimal("10"), Decimal("180"), Decimal("1"), Decimal("0.92")),
        Trade("2024-03-15", "BUY", Decimal("5"), Decimal("170"), Decimal("1"), Decimal("0.91")),
        Trade("2024-06-20", "SELL", Decimal("3"), Decimal("190"), Decimal("1"), Decimal("0.93")),
    ]

    gains = lifo_realized_gains(trades)

    assert len(gains) == 1

    gain = gains[0]

    assert gain.sell_date == "2024-06-20"
    assert gain.quantity == Decimal("3")
    assert gain.proceeds_eur == Decimal("529.17")
    assert gain.cost_basis_eur == Decimal("464.646")
    assert gain.realized_gain_eur == Decimal("64.524")
