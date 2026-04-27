"""Historical replay backtester.

For each rule the engine:
  1. Walks every bar via RuleEngine.replay() to collect signals
  2. For each signal at bar T, looks at bars (T+1 .. T+horizon)
  3. Computes return, max favourable / adverse excursion, and a hit flag
  4. Aggregates across signals into BacktestResult

A hit means close-to-close return cleared `hit_threshold_pct` in the rule's
expected direction (long: ≥ +threshold, short: ≤ −threshold).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from monitor.instruments import InstrumentType
from monitor.rules.base import Rule, Signal
from monitor.rules.engine import RuleEngine


@dataclass
class TradeOutcome:
    signal: Signal
    direction: str            # "long" | "short"
    horizon_bars: int
    entry_price: float
    exit_price: float
    return_pct: float         # close-to-close, signed
    mfe_pct: float            # max favourable excursion (in direction's favour)
    mae_pct: float            # max adverse excursion (against direction)
    hit: bool


@dataclass
class BacktestResult:
    rule_name: str
    timeframe: str
    direction: str
    horizon_bars: int
    hit_threshold_pct: float
    outcomes: list[TradeOutcome] = field(default_factory=list)

    @property
    def n_signals(self) -> int:
        return len(self.outcomes)

    @property
    def n_hits(self) -> int:
        return sum(1 for o in self.outcomes if o.hit)

    @property
    def win_rate(self) -> float:
        return self.n_hits / self.n_signals if self.outcomes else 0.0

    @property
    def avg_return_pct(self) -> float:
        return _avg(o.return_pct for o in self.outcomes)

    @property
    def avg_mfe_pct(self) -> float:
        return _avg(o.mfe_pct for o in self.outcomes)

    @property
    def avg_mae_pct(self) -> float:
        return _avg(o.mae_pct for o in self.outcomes)

    def summary_row(self) -> str:
        if not self.outcomes:
            return (
                f"{self.rule_name:30s} {self.timeframe:>4s} {self.direction:>5s}  "
                f"  -    (no signals)"
            )
        return (
            f"{self.rule_name:30s} {self.timeframe:>4s} {self.direction:>5s}  "
            f"n={self.n_signals:>3d}  win={self.win_rate * 100:>5.1f}%  "
            f"avgR={self.avg_return_pct:+6.2f}%  "
            f"MFE={self.avg_mfe_pct:+6.2f}%  MAE={self.avg_mae_pct:+6.2f}%"
        )


def _avg(seq) -> float:
    items = list(seq)
    return sum(items) / len(items) if items else 0.0


def _infer_direction(rule: Rule) -> str:
    """Read `rule.expected_direction` if available, else fall back to 'long'."""
    direction = getattr(rule, "expected_direction", None)
    return direction if direction in ("long", "short") else "long"


def _compute_outcome(
    sig: Signal,
    bars: pd.DataFrame,
    idx: int,
    direction: str,
    horizon: int,
    threshold_pct: float,
) -> TradeOutcome | None:
    if idx + horizon >= len(bars):
        return None  # not enough forward bars to evaluate
    entry = float(bars["close"].iloc[idx])
    if entry <= 0:
        return None

    forward = bars.iloc[idx + 1 : idx + 1 + horizon]
    exit_price = float(forward["close"].iloc[-1])
    return_pct = (exit_price - entry) / entry * 100.0

    if direction == "long":
        mfe = (float(forward["high"].max()) - entry) / entry * 100.0
        mae = (float(forward["low"].min()) - entry) / entry * 100.0
        hit = return_pct >= threshold_pct
    else:  # short
        mfe = (entry - float(forward["low"].min())) / entry * 100.0
        mae = (entry - float(forward["high"].max())) / entry * 100.0
        hit = return_pct <= -threshold_pct

    return TradeOutcome(
        signal=sig,
        direction=direction,
        horizon_bars=horizon,
        entry_price=entry,
        exit_price=exit_price,
        return_pct=return_pct,
        mfe_pct=mfe,
        mae_pct=mae,
        hit=hit,
    )


def _normalise_instruments(
    arg: Iterable[str] | dict[str, InstrumentType],
) -> dict[str, InstrumentType]:
    if isinstance(arg, dict):
        return dict(arg)
    return {s: InstrumentType.STOCK for s in arg}


def backtest_rule(
    rule: Rule,
    instruments: Iterable[str] | dict[str, InstrumentType],
    history: dict,
    horizon: int = 5,
    hit_threshold_pct: float = 0.5,
) -> BacktestResult:
    """Run one rule against `history` and return aggregated stats.

    `instruments` may be a list of symbols (assumed all stocks) or a
    {symbol: InstrumentType} mapping; the latter lets the rule's
    applies_to filter skip non-matching symbols.
    """
    direction = _infer_direction(rule)
    result = BacktestResult(
        rule_name=rule.name,
        timeframe=rule.timeframe,
        direction=direction,
        horizon_bars=horizon,
        hit_threshold_pct=hit_threshold_pct,
    )

    inst_map = _normalise_instruments(instruments)
    for sym, itype in inst_map.items():
        if itype not in rule.applies_to:
            continue

        bars = history.get(sym, {}).get(rule.timeframe)
        if bars is None or bars.empty:
            continue

        engine = RuleEngine([rule])  # fresh per-symbol so dedup state resets
        signals = engine.replay(sym, rule.timeframe, bars, itype=itype)
        if not signals:
            continue

        ts_to_idx = {ts: i for i, ts in enumerate(bars.index)}
        for sig in signals:
            idx = ts_to_idx.get(sig.bar_close_time)
            if idx is None:
                continue
            outcome = _compute_outcome(
                sig, bars, idx, direction, horizon, hit_threshold_pct
            )
            if outcome is not None:
                result.outcomes.append(outcome)

    return result


def backtest_yaml(
    yaml_path: Path | str,
    instruments: Iterable[str] | dict[str, InstrumentType],
    history: dict,
    horizon: int = 5,
    hit_threshold_pct: float = 0.5,
    include_disabled: bool = True,
) -> list[BacktestResult]:
    """Run every rule in the YAML config and return per-rule results.

    `include_disabled=True` means we backtest rules that are not currently
    live in production — the whole point is to compare candidates.
    """
    engine = RuleEngine.from_yaml(yaml_path, include_disabled=include_disabled)
    inst_map = _normalise_instruments(instruments)
    return [
        backtest_rule(rule, inst_map, history, horizon, hit_threshold_pct)
        for rule in engine._rules
    ]
