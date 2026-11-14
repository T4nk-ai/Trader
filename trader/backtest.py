"""Backtest engine.

A strategy produces a *target position* for every bar: a number between 0 (all cash)
and 1 (fully invested). The decision made with bar t's data is held from bar t's close
to bar t+1's close, so a strategy can never trade on a price it has not seen yet.

Every change in position pays fees plus slippage, both in basis points of the amount
traded. Results are always reported next to simply buying and holding the same asset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Costs:
    fee_bps: float = 5.0  # broker/exchange fee per trade, in basis points (0.05%)
    slippage_bps: float = 5.0  # assumed gap between expected and actual fill price

    @property
    def total(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000


@dataclass
class Result:
    name: str
    equity: pd.Series
    position: pd.Series
    trades: pd.DataFrame
    metrics: dict = field(default_factory=dict)


def periods_per_year(index: pd.DatetimeIndex) -> float:
    """Estimate bars per year from the data itself (works for daily, crypto and intraday)."""
    if len(index) < 2:
        return 252.0
    span_years = (index[-1] - index[0]).total_seconds() / (365.25 * 24 * 3600)
    if span_years <= 0:
        return 252.0
    return (len(index) - 1) / span_years


def run(prices: pd.Series, target: pd.Series, costs: Costs | None = None,
        name: str = "strategy", start_equity: float = 10_000.0) -> Result:
    """Simulate a long-only strategy on a close-price series."""
    costs = costs or Costs()
    prices = prices.astype(float).dropna()
    target = target.reindex(prices.index).ffill().fillna(0.0).clip(0.0, 1.0)

    bar_returns = prices.pct_change().fillna(0.0)
    held = target.shift(1).fillna(0.0)  # position decided at t-1 close, held over bar t
    turnover = held.diff().abs().fillna(held.abs())
    net = held * bar_returns - turnover * costs.total
    equity = start_equity * (1.0 + net).cumprod()

    trades = _trade_list(prices, held)
    res = Result(name=name, equity=equity, position=held, trades=trades)
    res.metrics = metrics(equity, held, trades, costs, turnover)
    return res


def buy_and_hold(prices: pd.Series, costs: Costs | None = None,
                 start_equity: float = 10_000.0) -> Result:
    target = pd.Series(1.0, index=prices.index)
    return run(prices, target, costs, name="buy and hold", start_equity=start_equity)


def _trade_list(prices: pd.Series, held: pd.Series) -> pd.DataFrame:
    """Round trips: entry when position goes from 0 to >0, exit when it returns to 0."""
    rows = []
    in_trade = False
    entry_time = entry_price = None
    prev = 0.0
    for t, pos in held.items():
        if not in_trade and pos > 0 and prev == 0:
            in_trade, entry_time = True, t
            # held over bar t means we bought at the previous bar's close
            loc = prices.index.get_loc(t)
            entry_price = prices.iloc[max(loc - 1, 0)]
        elif in_trade and pos == 0:
            loc = prices.index.get_loc(t)
            exit_price = prices.iloc[max(loc - 1, 0)]
            rows.append((entry_time, t, entry_price, exit_price, exit_price / entry_price - 1))
            in_trade = False
        prev = pos
    if in_trade:
        exit_price = prices.iloc[-1]
        rows.append((entry_time, prices.index[-1], entry_price, exit_price,
                     exit_price / entry_price - 1))
    return pd.DataFrame(rows, columns=["entry", "exit", "entry_price", "exit_price", "return"])


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def metrics(equity: pd.Series, held: pd.Series, trades: pd.DataFrame, costs: Costs,
            turnover: pd.Series) -> dict:
    ppy = periods_per_year(equity.index)
    rets = equity.pct_change().dropna()
    years = max(len(equity) - 1, 1) / ppy
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    cagr = float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 and total > -1 else -1.0
    vol = float(rets.std() * np.sqrt(ppy)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(ppy)) if rets.std() > 0 else 0.0
    return {
        "total_return": total,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown(equity),
        "trades": int(len(trades)),
        "win_rate": float((trades["return"] > 0).mean()) if len(trades) else 0.0,
        "time_in_market": float((held > 0).mean()),
        "cost_paid_pct": float(turnover.sum() * costs.total),
        "final_equity": float(equity.iloc[-1]),
    }
