"""Paper-trading runner. Run once a day (it is safe to run more often).

    python -m trader.runner              # one cycle: check rules, place paper orders
    python -m trader.runner --status     # show the paper account
    python -m trader.runner --kill "why" # stop all trading until the file is removed
    python -m trader.runner --export-trades trades.csv

Each cycle: load prices, ask each strategy for its target, turn the difference between
target and current holdings into orders, pass every order through the risk limits, fill
it on the paper broker, write it to the journal and send an alert.
"""

from __future__ import annotations

import argparse
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from . import alerts, data, strategies
from .broker import PaperBroker
from .journal import Journal
from .risk import AccountState, KillSwitch, Order, RiskLimits, RiskManager

STATE_DIR = Path("state")
REBALANCE_BAND = 0.20  # ignore drift smaller than 20% of the intended position


def load_config(path: Path) -> dict:
    cfg = tomllib.loads(Path(path).read_text())
    if cfg.get("mode") != "paper":
        raise SystemExit("Only paper mode exists. Live trading is not implemented.")
    total = sum(s["allocation"] for s in cfg["strategies"])
    if total > 1.0 + 1e-9:
        raise SystemExit(f"Allocations add up to {total:.0%}; they must not exceed 100%.")
    return cfg


def default_loader(symbol: str) -> pd.DataFrame:
    return data.load_yahoo(symbol, start="2015-01-01", refresh=True)


def default_fx() -> float:
    """US dollars per one Australian dollar."""
    try:
        return float(data.load_yahoo("AUDUSD=X", start="2024-01-01", refresh=True)["close"].iloc[-1])
    except Exception:
        return 0.65  # rough fallback so the journal still records an AUD value


def run_cycle(cfg: dict, state_dir: Path = STATE_DIR,
              loader: Callable[[str], pd.DataFrame] = default_loader,
              fx: Callable[[], float] = default_fx,
              now: datetime | None = None,
              notify: Callable[..., bool] = alerts.notify) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    state_dir = Path(state_dir)
    costs = cfg.get("costs", {})
    broker = PaperBroker(state_dir / "paper_account.json", cfg.get("starting_cash_usd", 10_000),
                         costs.get("fee_bps", 5), costs.get("slippage_bps", 5))
    journal = Journal(state_dir / "journal.sqlite")
    risk = RiskManager(RiskLimits(**cfg.get("risk", {})), KillSwitch(state_dir / "KILL"))

    # 1. Prices. If any symbol fails to load, do nothing this cycle rather than guess.
    frames, quotes = {}, {}
    try:
        for s in cfg["strategies"]:
            df = loader(s["symbol"])
            if df.empty:
                raise RuntimeError(f"no data for {s['symbol']}")
            age = (pd.Timestamp(today) - df.index[-1].normalize()).days
            if age > 7:
                raise RuntimeError(f"{s['symbol']} data is {age} days old")
            frames[s["symbol"]] = df
            quotes[s["symbol"]] = float(df["close"].iloc[-1])
    except Exception as exc:
        journal.event("error", f"data problem, no trades this cycle: {exc}")
        notify(f"Data problem, no trades this cycle: {exc}", "error")
        return {"status": "data_error", "error": str(exc)}

    def value_of(positions):
        return {sym: qty * quotes.get(sym, 0.0) for sym, qty in positions.items()}

    equity = broker.cash() + sum(value_of(broker.positions()).values())
    sod, peak, orders_today = journal.day_state(today.isoformat(), equity)
    peak = max(peak, equity)

    def account() -> AccountState:
        eq = broker.cash() + sum(value_of(broker.positions()).values())
        return AccountState(eq, sod, peak, value_of(broker.positions()), orders_today, today)

    stop = risk.account_check(account())
    if stop:
        journal.event("warn", stop)
        notify(stop, "warn")

    # 2. Orders: sells first so cash is free for buys.
    wanted = []
    for s in cfg["strategies"]:
        sym = s["symbol"]
        target = float(strategies.STRATEGIES[s["strategy"]](frames[sym]).iloc[-1])
        desired_value = target * s["allocation"] * equity
        current_value = broker.positions().get(sym, 0.0) * quotes[sym]
        diff = desired_value - current_value
        full_size = s["allocation"] * equity
        if desired_value == 0 and current_value > 0:
            wanted.append((s, "sell", broker.positions()[sym]))
        elif abs(diff) > REBALANCE_BAND * full_size:
            wanted.append((s, "buy" if diff > 0 else "sell", abs(diff) / quotes[sym]))
    wanted.sort(key=lambda w: w[1] != "sell")

    usd_per_aud = fx() if wanted else 0.65
    fills, rejected = [], []
    for s, side, qty in wanted:
        sym = s["symbol"]
        order = Order(sym, side, qty, quotes[sym])
        why = risk.order_check(order, account(), quotes[sym])
        if why:
            rejected.append((sym, side, why))
            journal.event("warn", f"rejected {side} {sym}: {why}")
            notify(f"Rejected {side} {sym}: {why}", "warn")
            continue
        fill = broker.submit(order, quotes[sym])
        orders_today += 1
        journal.trade(cfg["mode"], s["strategy"], sym, side, fill.quantity, fill.price,
                      fill.fee, usd_per_aud)
        journal.update_day(today.isoformat(), account().equity, orders_added=1)
        fills.append(fill)
        notify(f"PAPER {side.upper()} {fill.quantity:.6g} {sym} @ ${fill.price:,.2f} "
               f"({s['strategy']})", "trade")

    final = account()
    journal.update_day(today.isoformat(), final.equity)
    start_cash = cfg.get("starting_cash_usd", 10_000)
    holdings = ", ".join(f"{sym} ${val:,.0f}" for sym, val in final.positions_value.items()) or "none"
    summary = (f"Paper account ${final.equity:,.2f} ({final.equity / start_cash - 1:+.1%} since "
               f"start). Holdings: {holdings}. Cash ${broker.cash():,.0f}. "
               f"{len(fills)} trade(s), {len(rejected)} rejected.")
    journal.event("info", summary)
    notify(summary)
    return {"status": "ok", "equity": final.equity, "fills": fills, "rejected": rejected,
            "summary": summary}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config.toml")
    p.add_argument("--state-dir", default=str(STATE_DIR))
    p.add_argument("--status", action="store_true")
    p.add_argument("--kill", metavar="REASON")
    p.add_argument("--export-trades", metavar="CSV")
    args = p.parse_args(argv)
    state = Path(args.state_dir)

    if args.kill:
        KillSwitch(state / "KILL").trip(args.kill)
        alerts.notify(f"Kill switch turned ON: {args.kill}", "error")
        return
    if args.export_trades:
        Journal(state / "journal.sqlite").export_trades(Path(args.export_trades))
        print(f"Wrote {args.export_trades}")
        return
    cfg = load_config(Path(args.config))
    if args.status:
        b = PaperBroker(state / "paper_account.json", cfg.get("starting_cash_usd", 10_000))
        print(f"cash ${b.cash():,.2f}; positions {b.positions()}; "
              f"kill switch {'ON' if KillSwitch(state / 'KILL').tripped() else 'off'}")
        return
    result = run_cycle(cfg, state)
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
