# Trader

A private trading bot for stocks and bitcoin, built in stages. Each stage has to earn the next one.

| Phase | What it does | Money at risk |
|---|---|---|
| **1. Backtest** (built) | Tests strategies on price history, with costs, against buy-and-hold | None |
| **2. Paper trade** (built) | Runs the survivors daily with simulated money, hard risk limits, alerts | None |
| 3. Small live | Only if paper results beat buy-and-hold after costs, and only with the owner's go-ahead | Small, capped |

Planned brokers for an Australian resident: Interactive Brokers Australia for stocks, an AUSTRAC-registered exchange with trade-only API keys for bitcoin.

## Phase 1 strategies

| Name | Rule | Source |
|---|---|---|
| `trend_200` | Hold when price is above its 200-day average, cash when below | Classic baseline |
| `weekly_dip` | Buy when a close is 5%+ below last week's final close, hold 20 trading days | AlphaInsider reel |
| `ema_vwap` | Intraday: enter when a bar wicks through session VWAP and closes above it with the 9 EMA above VWAP; exit on a close below the EMA; flat overnight. Long only. | Roboquant / EMA + VWAP reel |

All strategies are long only with no leverage. A decision made on a bar's close is held from the next bar, so nothing trades on prices it hasn't seen yet. Each test is split into an earlier and a later period, because a rule that only works in one stretch is probably luck.

## Phase 1 results (14 Nov 2026)

Nothing beat buy-and-hold on return. The useful finding is about risk:

| Test | Strategy per year | Hold per year | Strategy worst drop | Hold worst drop |
|---|---|---|---|---|
| SPY, 200-day trend, 2005 on | +7.8% | +10.7% | -22% | -55% |
| BTC, 200-day trend, 2015 on | +55.1% | +57.0% | -70% | -83% |
| BTC, 200-day trend, 2021 on | +12.7% | +14.9% | -37% | -77% |
| AAPL, weekly 5% dip, 2005 on | +7.2% | +31.2% | -69% | -61% |
| SPY, weekly 5% dip, 2005 on | +1.6% | +10.7% | -39% | -55% |

The trend filter gives up some return for much smaller crashes. The weekly-dip rule from the first reel is clearly worse than holding and has been dropped. The EMA + VWAP intraday rule is untested until multi-year intraday data is available.

## Phase 2: paper trading

`config.toml` runs the 200-day trend filter on SPY (50% of the account) and BTC (25%) with a simulated $10,000. Every order goes through `trader/risk.py` first:

- no leverage and no shorting
- a cap on each position and on orders per day
- no new buys after a 3% down day
- a kill switch that trips automatically 20% below the account's peak, or by hand
- orders rejected if the price data looks stale or wrong

The **paper** workflow runs it every day at 22:30 UTC on GitHub and saves the account, journal and a `trades.csv` (with AUD values for tax) on the `paper-state` branch. There is no live-trading code in this repository.

```bash
python -m trader.runner            # one cycle
python -m trader.runner --status
python -m trader.runner --kill "reason"
```

Phone alerts: create a Telegram bot (see `trader/alerts.py`) and add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets (Settings → Secrets and variables → Actions).

See [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) and [docs/RUNBOOK.md](docs/RUNBOOK.md).

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
