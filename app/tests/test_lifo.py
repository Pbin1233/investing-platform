from decimal import Decimal
from app.portfolio.cost_basis import Trade, lifo_realized_gains

trades = [
    Trade("2024-01-10", "BUY", Decimal("10"), Decimal("180"), Decimal("1"), Decimal("0.92")),
    Trade("2024-03-15", "BUY", Decimal("5"), Decimal("170"), Decimal("1"), Decimal("0.91")),
    Trade("2024-06-20", "SELL", Decimal("3"), Decimal("190"), Decimal("1"), Decimal("0.93")),
]

gains = lifo_realized_gains(trades)

for gain in gains:
    print(gain)
