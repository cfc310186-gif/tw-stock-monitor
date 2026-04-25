"""CLI entry point: `monitor-backtest`.

Usage examples:
  monitor-backtest --mock                # synthetic data, no Shioaji login
  monitor-backtest --horizon 10 --threshold 1.0
  monitor-backtest --rules path/to/rules.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from monitor.backtest.engine import backtest_yaml
from monitor.broker.shioaji_client import ShioajiClient
from monitor.config import load_settings, load_watchlist
from monitor.data.historical import load_history
from monitor.data.mock import make_mock_history

_DEFAULT_RULES_YAML = Path(__file__).resolve().parent.parent.parent.parent / "config" / "rules.yaml"


def _print_report(results, threshold: float, horizon: int) -> None:
    print()
    print("═" * 90)
    print(f"  Backtest report — horizon={horizon} bars, hit-threshold=±{threshold:.2f}%")
    print("═" * 90)
    if not results:
        print("  (no rules in YAML)")
        return
    print(f"  {'rule':30s} {'tf':>4s} {'dir':>5s}  {'stats'}")
    print(f"  {'─' * 86}")
    for r in results:
        print(f"  {r.summary_row()}")
    print()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="monitor-backtest")
    parser.add_argument("--mock", action="store_true",
                        help="Use synthetic history (skips Shioaji login)")
    parser.add_argument("--horizon", type=int, default=5,
                        help="Look-forward bars after signal (default 5)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Hit threshold in %% (default 0.5)")
    parser.add_argument("--days", type=int, default=60,
                        help="Lookback days for history (default 60)")
    parser.add_argument("--rules", type=Path, default=_DEFAULT_RULES_YAML,
                        help=f"Path to rules YAML (default: {_DEFAULT_RULES_YAML})")
    parser.add_argument("--enabled-only", action="store_true",
                        help="Only backtest rules with enabled: true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    if args.mock:
        symbols = load_watchlist()
        logger.info("Mock mode: synthetic {}-day history for {} symbols",
                    args.days, len(symbols))
        history = make_mock_history(symbols, n_days=args.days)
    else:
        settings = load_settings()
        symbols = settings.symbols
        client = ShioajiClient(
            api_key=settings.shioaji_api_key,
            secret_key=settings.shioaji_secret_key,
            simulation=settings.shioaji_simulation,
        )
        client.login()
        try:
            history = load_history(client, symbols, lookback_days=args.days)
        finally:
            client.logout()

    if not history:
        logger.error("No history loaded — cannot backtest")
        return 1

    results = backtest_yaml(
        args.rules,
        symbols,
        history,
        horizon=args.horizon,
        hit_threshold_pct=args.threshold,
        include_disabled=not args.enabled_only,
    )
    _print_report(results, threshold=args.threshold, horizon=args.horizon)
    return 0


def backtest_cli() -> None:
    sys.exit(main())


if __name__ == "__main__":
    backtest_cli()
