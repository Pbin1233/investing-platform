from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass
class Trade:
    trade_date: str
    action: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    fx_rate_to_eur: Decimal


@dataclass
class RealizedGain:
    sell_date: str
    quantity: Decimal
    proceeds_eur: Decimal
    cost_basis_eur: Decimal
    realized_gain_eur: Decimal


def lifo_realized_gains(trades: Iterable[Trade]) -> list[RealizedGain]:
    lots: list[dict] = []
    realized: list[RealizedGain] = []

    sorted_trades = sorted(trades, key=lambda t: t.trade_date)

    for trade in sorted_trades:
        qty = Decimal(trade.quantity)
        price = Decimal(trade.price)
        fees = Decimal(trade.fees)
        fx = Decimal(trade.fx_rate_to_eur)

        if trade.action == "BUY":
            total_cost_eur = (qty * price + fees) * fx
            lots.append({
                "quantity": qty,
                "unit_cost_eur": total_cost_eur / qty,
            })

        elif trade.action == "SPLIT":
            current_qty = sum(lot["quantity"] for lot in lots)
            if current_qty <= 0:
                raise ValueError("Stock split cannot be applied without open lots")

            ratio = (current_qty + qty) / current_qty
            for lot in lots:
                lot["quantity"] *= ratio
                lot["unit_cost_eur"] /= ratio

        elif trade.action == "SELL":
            qty_to_sell = qty
            proceeds_eur = (qty * price - fees) * fx
            cost_basis_eur = Decimal("0")

            while qty_to_sell > 0:
                if not lots:
                    raise ValueError("Sell quantity exceeds available lots")

                lot = lots[-1]
                matched_qty = min(qty_to_sell, lot["quantity"])

                cost_basis_eur += matched_qty * lot["unit_cost_eur"]

                lot["quantity"] -= matched_qty
                qty_to_sell -= matched_qty

                if lot["quantity"] == 0:
                    lots.pop()

            realized.append(
                RealizedGain(
                    sell_date=trade.trade_date,
                    quantity=qty,
                    proceeds_eur=proceeds_eur,
                    cost_basis_eur=cost_basis_eur,
                    realized_gain_eur=proceeds_eur - cost_basis_eur,
                )
            )

        else:
            raise ValueError(f"Unsupported action: {trade.action}")

    return realized
