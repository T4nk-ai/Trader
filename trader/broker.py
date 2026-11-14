"""Brokers. Phase 2 uses only PaperBroker: simulated money, real prices.

A real broker adapter (Interactive Brokers for stocks, an Australian exchange for
bitcoin) will implement the same small interface in Phase 3, and only after the owner
explicitly approves live trading. There is deliberately no live adapter in this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol

from .risk import Order


@dataclass
class Fill:
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float


class Broker(Protocol):
    def cash(self) -> float: ...
    def positions(self) -> dict[str, float]: ...  # symbol -> quantity
    def submit(self, order: Order, quote: float) -> Fill: ...


@dataclass
class _PaperState:
    cash: float
    positions: dict[str, float] = field(default_factory=dict)


class PaperBroker:
    """Fills every order immediately at the quote plus slippage, minus a fee.

    State is saved to a JSON file so the paper account survives restarts.
    """

    def __init__(self, state_file: Path, starting_cash: float = 10_000.0,
                 fee_bps: float = 5.0, slippage_bps: float = 5.0):
        self.state_file = Path(state_file)
        self.fee = fee_bps / 10_000
        self.slip = slippage_bps / 10_000
        if self.state_file.exists():
            self._s = _PaperState(**json.loads(self.state_file.read_text()))
        else:
            self._s = _PaperState(cash=starting_cash)
            self._save()

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self._s), indent=2))
        tmp.replace(self.state_file)

    def cash(self) -> float:
        return self._s.cash

    def positions(self) -> dict[str, float]:
        return {k: v for k, v in self._s.positions.items() if abs(v) > 1e-12}

    def submit(self, order: Order, quote: float) -> Fill:
        sign = 1 if order.side == "buy" else -1
        price = quote * (1 + sign * self.slip)
        qty = order.quantity
        if order.side == "sell":
            qty = min(qty, self._s.positions.get(order.symbol, 0.0))
        notional = qty * price
        fee = notional * self.fee
        if order.side == "buy" and notional + fee > self._s.cash + 1e-9:
            # never spend money we don't have: shrink the order to fit
            qty = self._s.cash / (price * (1 + self.fee))
            notional, fee = qty * price, qty * price * self.fee
        self._s.cash -= sign * notional + fee
        self._s.positions[order.symbol] = self._s.positions.get(order.symbol, 0.0) + sign * qty
        self._save()
        return Fill(order.symbol, order.side, qty, price, fee)
