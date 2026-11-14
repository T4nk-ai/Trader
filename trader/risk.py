"""Hard risk limits. Every order passes through here before it reaches a broker.

These rules protect the account from the bot itself: bugs, bad data and bad luck.
They are deliberately simple and conservative; loosen them only on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class RiskLimits:
    max_position_frac: float = 0.25  # one symbol may be at most 25% of the account
    max_gross_exposure: float = 1.0  # total invested <= account value: no leverage, ever
    daily_loss_limit: float = 0.02  # stop for the day after losing 2% of start-of-day value
    max_drawdown_limit: float = 0.15  # trip the kill switch 15% below the account's peak
    max_orders_per_day: int = 10  # a bug can't fire hundreds of trades
    max_price_deviation: float = 0.05  # reject if quote is >5% from last known close
    allow_short: bool = False


@dataclass
class Order:
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    ref_price: float  # the price the decision was based on

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.ref_price


@dataclass
class AccountState:
    equity: float
    start_of_day_equity: float
    peak_equity: float
    positions_value: dict[str, float]  # symbol -> market value
    orders_today: int
    today: date


class KillSwitch:
    """A file on disk. If it exists, the bot will not buy anything (it may still sell).

    Trip it with `python -m trader.runner --kill` (or by creating the file). Clearing
    it is a deliberate manual step: delete the file after you've checked what happened.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def tripped(self) -> bool:
        return self.path.exists()

    def reason(self) -> str:
        return self.path.read_text().strip() if self.tripped() else ""

    def trip(self, reason: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(reason + "\n")


class RiskManager:
    def __init__(self, limits: RiskLimits, kill_switch: KillSwitch):
        self.limits = limits
        self.kill = kill_switch

    def account_check(self, s: AccountState) -> str | None:
        """Checks that stop all trading. Returns a reason, or None if OK."""
        if self.kill.tripped():
            return f"kill switch is on: {self.kill.reason()}"
        if s.peak_equity > 0 and s.equity < s.peak_equity * (1 - self.limits.max_drawdown_limit):
            reason = (f"drawdown limit hit: equity {s.equity:,.2f} is more than "
                      f"{self.limits.max_drawdown_limit:.0%} below peak {s.peak_equity:,.2f}")
            self.kill.trip(reason)
            return reason
        if s.start_of_day_equity > 0 and \
                s.equity < s.start_of_day_equity * (1 - self.limits.daily_loss_limit):
            return f"daily loss limit hit ({self.limits.daily_loss_limit:.0%}); no new trades today"
        return None

    def order_check(self, o: Order, s: AccountState, quote: float) -> str | None:
        """Per-order checks. Returns a reason to reject, or None if OK."""
        stop = self.account_check(s)
        # A stop blocks every buy. Sells are still allowed because they only reduce
        # risk: the strategy can still exit a falling position while buying is frozen.
        if stop and o.side == "buy":
            return stop
        if o.quantity <= 0:
            return "quantity must be positive"
        if s.orders_today >= self.limits.max_orders_per_day:
            return f"max {self.limits.max_orders_per_day} orders per day reached"
        if quote <= 0 or abs(quote / o.ref_price - 1) > self.limits.max_price_deviation:
            return (f"price check failed: quote {quote} vs reference {o.ref_price} "
                    f"(> {self.limits.max_price_deviation:.0%} apart, data may be stale)")
        held = s.positions_value.get(o.symbol, 0.0)
        if o.side == "sell":
            if not self.limits.allow_short and o.notional > held * (1 + 1e-6) + 1e-9:
                return "would go short; shorting is disabled"
            return None
        new_pos = held + o.notional
        if new_pos > s.equity * self.limits.max_position_frac * (1 + 1e-6):
            return (f"position in {o.symbol} would be {new_pos / s.equity:.0%} of the account; "
                    f"limit is {self.limits.max_position_frac:.0%}")
        gross = sum(s.positions_value.values()) + o.notional
        if gross > s.equity * self.limits.max_gross_exposure * (1 + 1e-6):
            return "would use leverage; total exposure limit reached"
        return None
