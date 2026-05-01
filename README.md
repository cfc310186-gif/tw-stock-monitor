# TW Stock Monitor

Intraday monitor for Taiwan stocks and futures. It loads a typed watchlist,
bootstraps historical 1-minute bars, builds rolling multi-timeframe bars,
evaluates technical rules, persists fired signals to SQLite, and sends
Telegram alerts.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item config\.env.example config\.env
```

Fill `config/.env` with Shioaji and Telegram credentials.

## Commands

```powershell
monitor
monitor-backtest --mock
monitor-backtest --horizon 10 --threshold 1.0
indicators_demo --mock
overseas_quote_check
pytest
ruff check src tests
```

Runtime state is written to `data/signals.db` by default. Override it with
`MONITOR_DB_PATH`. Override the rule file with `MONITOR_RULES_PATH`.

## Configuration

- `config/watchlist.yaml`: symbols grouped by instrument type.
- `config/rules.yaml`: enabled alert rules, timeframe, market scope, volume
  threshold, and cooldown.

Supported rule families today:

- `bb_reversal`
- `ma_cross_reversal`
- `range_breakout`

Overseas futures require the optional IB dependency and a running IB Gateway or
TWS process:

```powershell
pip install -e ".[ib]"
```

Add symbols under `overseas_futures` in `config/watchlist.yaml`, for example:

```yaml
overseas_futures:
  - "MNQ"
  - "MCL@NYMEX"
```

Use `SYMBOL@EXCHANGE` when the default exchange map does not know the product.
For first connection tests, keep `IB_READONLY=true`. `IB_MARKET_DATA_TYPE=1`
requests live market data. Use `3` for delayed data when the account does not
have live market-data permissions. `IB_MARKET_DATA_WAIT_SECONDS` controls how
long the quote checker waits for the first tick after subscribing.

Before running the full monitor, validate IB quotes only:

```powershell
overseas_quote_check
```

## Docker

```powershell
docker compose -f docker/compose.yml up -d --build
```

The compose file mounts `config/` read-only and persists SQLite data under the
Docker volume mounted at `/app/data`.
