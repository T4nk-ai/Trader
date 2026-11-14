from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trader import runner
from trader.broker import PaperBroker
from trader.journal import Journal
from trader.risk import AccountState, KillSwitch, Order, RiskLimits, RiskManager

NOW = datetime(2024, 6, 3, 12, tzinfo=timezone.utc)


def frame(prices, end="2024-06-03"):
    idx = pd.bdate_range(end=end, periods=len(prices))
    c = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0})


UP = frame(np.linspace(100, 200, 300))
DOWN = frame(np.linspace(200, 100, 300))


def cfg(**risk):
    return {"mode": "paper", "starting_cash_usd": 10_000,
            "strategies": [{"symbol": "AAA", "strategy": "trend_200", "allocation": 0.5}],
            "costs": {"fee_bps": 0, "slippage_bps": 0},
            "risk": {"max_position_frac": 0.5, **risk}}


def cycle(tmp_path, df, config=None, now=NOW):
    msgs = []
    out = runner.run_cycle(config or cfg(), tmp_path, loader=lambda s: df, fx=lambda: 0.65,
                           now=now, notify=lambda t, level="info": msgs.append((level, t)))
    return out, msgs


def state(equity=10_000, sod=10_000, peak=10_000, positions=None, orders=0):
    return AccountState(equity, sod, peak, positions or {}, orders, date(2024, 6, 3))


def manager(tmp_path, **kw):
    return RiskManager(RiskLimits(**kw), KillSwitch(tmp_path / "KILL"))


# --- risk limits -----------------------------------------------------------------

def test_position_size_limit(tmp_path):
    rm = manager(tmp_path, max_position_frac=0.25)
    assert rm.order_check(Order("A", "buy", 20, 100), state(), 100) is None
    assert "limit is 25%" in rm.order_check(Order("A", "buy", 30, 100), state(), 100)


def test_no_leverage(tmp_path):
    rm = manager(tmp_path, max_position_frac=1.0)
    s = state(positions={"A": 9_000})
    assert "leverage" in rm.order_check(Order("B", "buy", 20, 100), s, 100)


def test_no_shorting(tmp_path):
    rm = manager(tmp_path)
    assert "short" in rm.order_check(Order("A", "sell", 5, 100), state(), 100)


def test_stale_price_rejected(tmp_path):
    rm = manager(tmp_path)
    assert "price check" in rm.order_check(Order("A", "buy", 1, 100), state(), 120)


def test_order_count_limit(tmp_path):
    rm = manager(tmp_path, max_orders_per_day=3)
    assert "orders per day" in rm.order_check(Order("A", "buy", 1, 100), state(orders=3), 100)


def test_daily_loss_blocks_buys_but_allows_sells(tmp_path):
    rm = manager(tmp_path, daily_loss_limit=0.02)
    s = state(equity=9_700, positions={"A": 2_000})
    assert "daily loss" in rm.order_check(Order("B", "buy", 1, 100), s, 100)
    assert rm.order_check(Order("A", "sell", 10, 100), s, 100) is None


def test_drawdown_trips_kill_switch_and_blocks_buys(tmp_path):
    rm = manager(tmp_path, max_drawdown_limit=0.15)
    s = state(equity=8_000, sod=8_000, peak=10_000, positions={"A": 2_000})
    assert "drawdown" in rm.account_check(s)
    assert rm.kill.tripped()
    assert "kill switch" in rm.order_check(Order("B", "buy", 1, 100), s, 100)
    assert rm.order_check(Order("A", "sell", 10, 100), s, 100) is None


# --- paper broker ----------------------------------------------------------------

def test_paper_broker_fills_and_persists(tmp_path):
    f = tmp_path / "acct.json"
    b = PaperBroker(f, 1_000, fee_bps=10, slippage_bps=10)
    fill = b.submit(Order("A", "buy", 5, 100), 100)
    assert fill.price == pytest.approx(100.1)
    assert b.cash() == pytest.approx(1_000 - 500.5 - 0.5005)
    assert PaperBroker(f).positions() == {"A": 5}


def test_paper_broker_never_overspends_or_oversells(tmp_path):
    b = PaperBroker(tmp_path / "a.json", 1_000, fee_bps=10, slippage_bps=0)
    b.submit(Order("A", "buy", 100, 100), 100)
    assert b.cash() >= -1e-9
    b.submit(Order("A", "sell", 1_000, 100), 100)
    assert b.positions() == {}


# --- full cycle ------------------------------------------------------------------

def test_cycle_buys_in_uptrend_and_journals_in_aud(tmp_path):
    out, msgs = cycle(tmp_path, UP)
    assert out["status"] == "ok" and len(out["fills"]) == 1
    assert out["fills"][0].quantity == pytest.approx(25)  # 50% of 10k at $200
    row = Journal(tmp_path / "journal.sqlite").db.execute(
        "SELECT side, value_aud FROM trades").fetchone()
    assert row[0] == "buy" and row[1] == pytest.approx(5_000 / 0.65)
    assert any(level == "trade" for level, _ in msgs)


def test_cycle_is_idempotent(tmp_path):
    cycle(tmp_path, UP)
    out, _ = cycle(tmp_path, UP)
    assert out["fills"] == []


def test_cycle_stays_in_cash_in_downtrend_then_sells_after_reversal(tmp_path):
    out, _ = cycle(tmp_path, DOWN)
    assert out["fills"] == []
    cycle(tmp_path, UP)
    out, _ = cycle(tmp_path, frame(list(np.linspace(100, 200, 250)) + [120] * 50))
    assert out["fills"][0].side == "sell"
    assert PaperBroker(tmp_path / "paper_account.json").positions() == {}
    # the 40% fall also tripped the drawdown kill switch: no re-buying until a human clears it
    assert KillSwitch(tmp_path / "KILL").tripped()
    out, _ = cycle(tmp_path, UP)
    assert out["fills"] == [] and len(out["rejected"]) == 1


def test_cycle_does_nothing_when_kill_switch_on(tmp_path):
    KillSwitch(tmp_path / "KILL").trip("testing")
    out, msgs = cycle(tmp_path, UP)
    assert out["fills"] == [] and len(out["rejected"]) == 1
    assert any("kill switch" in t for _, t in msgs)


def test_cycle_does_nothing_on_stale_or_missing_data(tmp_path):
    out, msgs = cycle(tmp_path, frame(np.linspace(100, 200, 300), end="2024-04-01"))
    assert out["status"] == "data_error"
    assert any(level == "error" for level, _ in msgs)
    assert not (tmp_path / "paper_account.json").exists() or \
        PaperBroker(tmp_path / "paper_account.json").positions() == {}


def test_config_rejects_live_mode_and_over_allocation(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('mode = "live"\n[[strategies]]\nsymbol="A"\nstrategy="trend_200"\nallocation=0.5\n')
    with pytest.raises(SystemExit):
        runner.load_config(p)
    p.write_text('mode = "paper"\n[[strategies]]\nsymbol="A"\nstrategy="trend_200"\nallocation=0.7\n'
                 '[[strategies]]\nsymbol="B"\nstrategy="trend_200"\nallocation=0.7\n')
    with pytest.raises(SystemExit):
        runner.load_config(p)


def test_real_config_loads():
    cfg_ = runner.load_config("config.toml")
    assert cfg_["mode"] == "paper"
