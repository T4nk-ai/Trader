import numpy as np
import pandas as pd
import pytest

from trader import backtest, strategies, report


def daily(prices, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(prices))
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 1_000.0})


NO_COSTS = backtest.Costs(0, 0)


def test_buy_and_hold_matches_price_change_without_costs():
    df = daily(np.linspace(100, 200, 300))
    res = backtest.buy_and_hold(df["close"], NO_COSTS)
    # the first bar is spent buying, so the return is from the first close onward
    assert res.metrics["total_return"] == pytest.approx(200 / 100 - 1, rel=1e-9)


def test_costs_reduce_returns():
    df = daily(np.linspace(100, 200, 300))
    free = backtest.buy_and_hold(df["close"], NO_COSTS).metrics["final_equity"]
    paid = backtest.buy_and_hold(df["close"], backtest.Costs(10, 10)).metrics["final_equity"]
    assert paid < free
    assert paid == pytest.approx(free * (1 - 0.002), rel=1e-4)


def test_no_lookahead_signal_on_jump_bar_does_not_capture_jump():
    # Price jumps 10% on day 5. A strategy that buys *because* of that close must not
    # earn the jump itself.
    prices = [100] * 5 + [110] * 5
    df = daily(prices)
    target = (df["close"] > 105).astype(float)
    res = backtest.run(df["close"], target, NO_COSTS)
    assert res.metrics["total_return"] == pytest.approx(0.0)


def test_cash_strategy_stays_flat():
    df = daily(np.linspace(100, 50, 100))
    res = backtest.run(df["close"], pd.Series(0.0, index=df.index), NO_COSTS)
    assert res.metrics["total_return"] == 0
    assert res.metrics["trades"] == 0


def test_max_drawdown():
    eq = pd.Series([100, 120, 60, 90], index=pd.bdate_range("2020-01-01", periods=4))
    assert backtest.max_drawdown(eq) == pytest.approx(-0.5)


def test_trend_filter_goes_to_cash_in_downtrend():
    prices = list(np.linspace(100, 200, 250)) + list(np.linspace(200, 80, 250))
    df = daily(prices)
    target = strategies.trend_filter(df, window=50)
    assert target.iloc[:49].sum() == 0  # not enough history yet
    assert target.iloc[200] == 1.0
    assert target.iloc[-1] == 0.0
    s = backtest.run(df["close"], target, NO_COSTS)
    b = backtest.buy_and_hold(df["close"], NO_COSTS)
    assert s.metrics["max_drawdown"] > b.metrics["max_drawdown"]


def test_weekly_dip_triggers_and_holds_fixed_days():
    idx = pd.bdate_range("2024-01-01", periods=30)  # starts on a Monday
    close = pd.Series(100.0, index=idx)
    close.iloc[7] = 94.0  # Wednesday of week 2, 6% below last Friday's 100
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                       "volume": 1.0})
    target = strategies.weekly_dip(df, drop=0.05, hold_days=3)
    assert list(target.iloc[6:11]) == [0, 1, 1, 1, 0]


def test_weekly_dip_ignores_small_drops():
    df = daily([100] * 6 + [97] * 10, start="2024-01-01")
    assert strategies.weekly_dip(df, drop=0.05).sum() == 0


def intraday_day(day, closes, lows, volume=100.0):
    idx = pd.date_range(f"{day} 09:30", periods=len(closes), freq="3min")
    c = pd.Series(closes, index=idx, dtype=float)
    lo = pd.Series(lows, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 0.1, "low": lo, "close": c,
                         "volume": volume})


def test_session_vwap_resets_each_day():
    d1 = intraday_day("2024-03-04", [100] * 5, [99.9] * 5)
    d2 = intraday_day("2024-03-05", [200] * 5, [199.9] * 5)
    vwap = strategies.session_vwap(pd.concat([d1, d2]))
    assert vwap.iloc[4] == pytest.approx(100.0, abs=0.1)
    assert vwap.iloc[5] == pytest.approx(200.0, abs=0.1)


def test_ema_vwap_enters_on_vwap_wick_and_is_flat_overnight():
    closes = [100, 101, 102, 103, 104, 105, 104, 105, 106, 107, 103, 102]
    lows = list(closes)  # no wicks except the one below
    lows[6] = 95  # wick down through VWAP, close stays above
    df = intraday_day("2024-03-04", closes, lows)
    target = strategies.ema_vwap(df, ema_len=3)
    assert target.iloc[5] == 0
    assert target.iloc[6] == 1  # entry signal on the wick bar
    assert target.iloc[10] == 0  # close back below the EMA -> out
    assert target.iloc[-1] == 0  # flat at end of day


def test_report_rows_compare_with_buy_and_hold():
    df = daily(np.linspace(100, 200, 300))
    rows = report._rows("Full", df, "trend_200", NO_COSTS, None)
    assert "buy and hold" in rows[1]
    assert "verdict" in rows[2]
