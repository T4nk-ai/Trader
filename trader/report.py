"""Run the Phase 1 backtests and write a report.

    python -m trader.report                 # default study, downloads data
    python -m trader.report --csv my.csv --strategy ema_vwap --name SPY-3m

Writes reports/report.md and one equity chart per test. Every strategy is shown next to
buy-and-hold, and each test is split into an earlier and a later period, because a rule
that only works in one stretch is probably luck or curve-fitting.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import backtest, data, strategies

REPORT_DIR = Path("reports")


@dataclass
class Study:
    symbol: str
    strategy: str
    start: str = "2005-01-01"
    split: str = "2018-01-01"  # results are also shown before and after this date
    kwargs: dict | None = None


DEFAULT_STUDIES = [
    Study("SPY", "trend_200"),
    Study("BTC-USD", "trend_200", start="2015-01-01", split="2021-01-01"),
    Study("AAPL", "weekly_dip", kwargs={"hold_days": 20}),
    Study("SPY", "weekly_dip", kwargs={"hold_days": 20}),
]


def evaluate(df: pd.DataFrame, strategy: str, costs: backtest.Costs,
             kwargs: dict | None = None) -> tuple[backtest.Result, backtest.Result]:
    target = strategies.STRATEGIES[strategy](df, **(kwargs or {}))
    strat = backtest.run(df["close"], target, costs, name=strategy)
    bench = backtest.buy_and_hold(df["close"], costs)
    return strat, bench


def _fmt(m: dict) -> str:
    return (f"{m['total_return']:+.0%} | {m['cagr']:+.1%} | {m['max_drawdown']:.0%} | "
            f"{m['sharpe']:.2f} | {m['trades']} | {m['time_in_market']:.0%}")


def _rows(label: str, df: pd.DataFrame, strategy: str, costs, kwargs) -> list[str]:
    if len(df) < 50:
        return [f"| {label} | not enough data | | | | | |"]
    s, b = evaluate(df, strategy, costs, kwargs)
    verdict = "beats" if s.metrics["cagr"] > b.metrics["cagr"] else "loses to"
    return [
        f"| {label}: {strategy} | {_fmt(s.metrics)} |",
        f"| {label}: buy and hold | {_fmt(b.metrics)} |",
        f"| {label}: verdict | strategy {verdict} buy and hold on yearly return | | | | | |",
    ]


def _chart(name: str, strat: backtest.Result, bench: backtest.Result) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(strat.equity.index, strat.equity, label=strat.name)
    ax.plot(bench.equity.index, bench.equity, label="buy and hold")
    ax.set_yscale("log")
    ax.set_title(name)
    ax.legend()
    ax.grid(alpha=0.3)
    path = REPORT_DIR / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path.name


def study_section(name: str, df: pd.DataFrame, study: Study, costs) -> list[str]:
    split = pd.Timestamp(study.split)
    lines = [f"## {name}", "",
             "| Test | Total | Per year | Worst drop | Sharpe | Trades | Invested |",
             "|---|---|---|---|---|---|---|"]
    lines += _rows("Full period", df, study.strategy, costs, study.kwargs)
    lines += _rows(f"Before {split.date()}", df[df.index < split], study.strategy, costs,
                   study.kwargs)
    lines += _rows(f"From {split.date()}", df[df.index >= split], study.strategy, costs,
                   study.kwargs)
    s, b = evaluate(df, study.strategy, costs, study.kwargs)
    chart = _chart(name, s, b)
    if chart:
        lines += ["", f"![{name}]({chart})"]
    return lines + [""]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--csv", help="run one strategy on your own OHLCV CSV instead")
    p.add_argument("--strategy", default="ema_vwap", choices=list(strategies.STRATEGIES))
    p.add_argument("--name", default="custom")
    p.add_argument("--split", default="2023-01-01")
    args = p.parse_args(argv)

    costs = backtest.Costs(args.fee_bps, args.slippage_bps)
    REPORT_DIR.mkdir(exist_ok=True)
    lines = ["# Phase 1 backtest report", "",
             f"Costs per trade: {args.fee_bps} bps fee + {args.slippage_bps} bps slippage. "
             "Long only, no leverage. Past results do not predict future returns.", ""]

    if args.csv:
        df = data.load_csv(args.csv)
        study = Study(args.name, args.strategy, split=args.split)
        lines += study_section(args.name, df, study, costs)
    else:
        for st in DEFAULT_STUDIES:
            name = f"{st.symbol}-{st.strategy}"
            try:
                df = data.load_yahoo(st.symbol, start=st.start)
            except Exception as exc:  # network or symbol problems shouldn't stop the rest
                lines += [f"## {name}", "", f"Data download failed: {exc}", ""]
                continue
            lines += study_section(name, df, st, costs)

    out = REPORT_DIR / "report.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
