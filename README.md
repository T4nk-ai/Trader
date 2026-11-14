# Trader

A private trading bot for stocks and bitcoin, built in stages. Each stage has to earn the next one.

| Phase | What it does | Money at risk |
|---|---|---|
| **1. Backtest** (this code) | Tests strategies on price history, with costs, against buy-and-hold | None |
| 2. Paper trade | Runs the survivors live with simulated money, hard risk limits, alerts | None |
| 3. Small live | Only if paper results beat buy-and-hold after costs, and only with the owner's go-ahead | Small, capped |

Planned brokers for an Australian resident: Interactive Brokers Australia for stocks, an AUSTRAC-registered exchange with trade-only API keys for bitcoin.

## Phase 1 strategies

| Name | Rule | Source |
|---|---|---|
| `trend_200` | Hold when price is above its 200-day average, cash when below | Classic baseline |
| `weekly_dip` | Buy when a close is 5%+ below last week's final close, hold 20 trading days | AlphaInsider reel |
| `ema_vwap` | Intraday: enter when a bar wicks through session VWAP and closes above it with the 9 EMA above VWAP; exit on a close below the EMA; flat overnight. Long only. | Roboquant / EMA + VWAP reel |

All strategies are long only with no leverage. A decision made on a bar's close is held from the next bar, so nothing trades on prices it hasn't seen yet. Each test is split into an earlier and a later period, because a rule that only works in one stretch is probably luck.

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                      # engine and strategy tests
python -m trader.report        # downloads data, writes reports/report.md and charts
```

No computer handy: in GitHub, open **Actions → backtest → Run workflow**. The report shows on the run page and the charts download as an artifact.

### Testing the intraday strategy properly

Free data only has about 60 days of intraday bars, which is far too short. Export several years of 3- or 5-minute SPY bars (for example from Interactive Brokers) to a CSV with `datetime,open,high,low,close,volume` columns, then:

```bash
python -m trader.report --csv spy_3min.csv --strategy ema_vwap --name SPY-3m --split 2023-01-01
```

## Safety rules for this repository

- Keep the repository **private**.
- Never commit API keys. Copy `.env.example` to `.env` (ignored by git). Phase 1 needs no keys at all.
- Turn on GitHub secret scanning with push protection and Dependabot alerts (Settings → Code security).
- Broker and exchange keys used later must be **trade-only, with withdrawals disabled**, and IP-locked where possible.

Past performance does not predict future returns. This is a research tool, not financial advice.
