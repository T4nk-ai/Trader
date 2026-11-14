"""Price data. Downloads free history from Yahoo Finance and caches it in ./data/.

Free intraday data is limited (Yahoo keeps only about 60 days of 5-minute bars), which
is too short to judge an intraday strategy. For a proper test of the EMA + VWAP rule,
load longer intraday history from a CSV (for example exported from Interactive Brokers)
with `load_csv`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
COLUMNS = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    if "adj close" in df.columns:
        # Use dividend/split adjusted prices so buy-and-hold is measured fairly.
        factor = df["adj close"] / df["close"]
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col] * factor
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["close"])
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    return df.sort_index()


def load_yahoo(symbol: str, start: str = "2000-01-01", end: str | None = None,
               interval: str = "1d", refresh: bool = False) -> pd.DataFrame:
    import yfinance as yf

    DATA_DIR.mkdir(exist_ok=True)
    cache = DATA_DIR / f"{symbol.replace('/', '_')}_{interval}_{start}_{end or 'latest'}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    raw = yf.download(symbol, start=start, end=end, interval=interval,
                      auto_adjust=False, progress=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"No data returned for {symbol}")
    df = _normalise(raw)
    df.to_csv(cache)
    return df


def load_csv(path: str | Path) -> pd.DataFrame:
    """CSV with a datetime first column and open/high/low/close/volume columns."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return _normalise(df)
