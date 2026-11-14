"""Strategies. Each takes a price DataFrame (columns: open, high, low, close[, volume])
and returns a target position series (0 = cash, 1 = fully invested), long only.

Every value at bar t uses only data up to and including bar t. The backtest engine
then holds it from the next bar, so there is no look-ahead.
"""

from __future__ import annotations

import pandas as pd


def trend_filter(df: pd.DataFrame, window: int = 200) -> pd.Series:
    """Hold when the close is above its moving average, cash when below.

    A well-known, simple rule that aims to sidestep long bear markets. Mostly useful as
    a baseline: if fancier strategies can't beat this and buy-and-hold, drop them.
    """
    close = df["close"]
    ma = close.rolling(window, min_periods=window).mean()
    return (close > ma).astype(float).where(ma.notna(), 0.0)


def weekly_dip(df: pd.DataFrame, drop: float = 0.05, hold_days: int = 20) -> pd.Series:
    """From the first reel: buy when a daily close is `drop` or more below last week's
    final close, then hold for a fixed number of trading days. A new signal while
    holding restarts the clock.
    """
    close = df["close"]
    week = close.index.to_period("W-FRI")
    week_last = close.groupby(week).last()
    prev_week_close = pd.Series(week, index=close.index).map(week_last.shift(1))
    signal = close <= prev_week_close * (1.0 - drop)

    target = pd.Series(0.0, index=close.index)
    remaining = 0
    for i, fire in enumerate(signal.to_numpy()):
        if fire:
            remaining = hold_days
        if remaining > 0:
            target.iloc[i] = 1.0
            remaining -= 1
    return target


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP anchored at the start of each trading day."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].astype(float)
    day = df.index.normalize()
    pv = (typical * vol).groupby(day).cumsum()
    v = vol.groupby(day).cumsum()
    return (pv / v.where(v > 0)).ffill()


def ema_vwap(df: pd.DataFrame, ema_len: int = 9) -> pd.Series:
    """From the second reel, long-only version (no puts, no futures, no leverage).

    Intraday bars (the reel uses 3-minute). Enter when a bar wicks down through the
    session VWAP but closes back above it while the EMA is above VWAP (buyers defending
    VWAP in an uptrend). Exit when a bar closes below the EMA. Always flat at the last
    bar of each day, so nothing is held overnight.
    """
    close = df["close"]
    ema = close.ewm(span=ema_len, adjust=False).mean()
    vwap = session_vwap(df)
    entry = (df["low"] <= vwap) & (close > vwap) & (ema > vwap)
    exit_ = close < ema
    day = df.index.normalize()
    last_bar = pd.Series(day, index=df.index) != pd.Series(day, index=df.index).shift(-1)

    target = pd.Series(0.0, index=df.index)
    pos = 0.0
    for i in range(len(df)):
        if pos == 0.0 and entry.iloc[i]:
            pos = 1.0
        elif pos == 1.0 and exit_.iloc[i]:
            pos = 0.0
        if last_bar.iloc[i]:
            pos = 0.0
        target.iloc[i] = pos
    return target


STRATEGIES = {
    "trend_200": trend_filter,
    "weekly_dip": weekly_dip,
    "ema_vwap": ema_vwap,
}
