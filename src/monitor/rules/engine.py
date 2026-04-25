from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
from loguru import logger

from monitor.rules.base import Rule, Signal
from monitor.rules.bb_reversal import BbReversalRule

_RULE_CLASSES: dict[str, type[Rule]] = {
    "bb_reversal": BbReversalRule,
}

_GLOBAL_COOLDOWN_MINUTES = 10


class RuleEngine:
    """Evaluates rules against K-bar data with dedup and cooldown guards.

    Cooldown layers (three independent gates):
      1. Bar-level dedup   — (sym, rule, tf, bar_ts) fires at most once per bar
      2. Per-rule cooldown — same rule on same symbol is silenced for N minutes
      3. Global cooldown   — any signal on a symbol silences all rules for 10 min
    """

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules
        self._seen: set[tuple] = set()                     # bar-level dedup keys
        self._rule_last: dict[tuple, datetime] = {}        # (sym, rule, tf) → triggered_at
        self._global_last: dict[str, datetime] = {}        # symbol → triggered_at

    @classmethod
    def from_yaml(cls, path: Path | str) -> "RuleEngine":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        rules: list[Rule] = []
        for cfg in raw:
            if not cfg.get("enabled", True):
                continue
            matched = False
            for key, rule_cls in _RULE_CLASSES.items():
                if key in cfg.get("name", ""):
                    rules.append(rule_cls.from_config(cfg))
                    matched = True
                    break
            if not matched:
                logger.warning("No rule class matched for '{}', skipped", cfg.get("name"))
        logger.info("RuleEngine loaded {} rule(s)", len(rules))
        return cls(rules)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        symbol: str,
        timeframe: str,
        bars: pd.DataFrame,
        now: datetime | None = None,
    ) -> list[Signal]:
        """Evaluate all matching rules and return un-throttled signals."""
        if now is None:
            now = datetime.now()

        signals: list[Signal] = []
        for rule in self._rules:
            if rule.timeframe != timeframe:
                continue

            sig = rule.evaluate(symbol, bars)
            if sig is None:
                continue

            # Gate 1: bar-level dedup
            dedup = sig.dedup_key()
            if dedup in self._seen:
                continue

            # Gate 2: per-rule cooldown
            cool_key = (symbol, rule.name, timeframe)
            last_rule = self._rule_last.get(cool_key)
            if last_rule and (now - last_rule) < timedelta(minutes=rule.cooldown_minutes):
                logger.debug("{}/{}/{} rule cooldown", symbol, rule.name, timeframe)
                continue

            # Gate 3: global per-symbol cooldown
            last_global = self._global_last.get(symbol)
            if last_global and (now - last_global) < timedelta(minutes=_GLOBAL_COOLDOWN_MINUTES):
                logger.debug("{} global cooldown", symbol)
                continue

            self._seen.add(dedup)
            self._rule_last[cool_key] = now
            self._global_last[symbol] = now
            signals.append(sig)

        return signals

    def replay(
        self,
        symbol: str,
        timeframe: str,
        all_bars: pd.DataFrame,
    ) -> list[Signal]:
        """Walk through every bar in all_bars and collect all signals.

        Useful for historical back-test / smoke-test without cooldown.
        Cooldown is disabled to surface every trigger point.
        """
        signals: list[Signal] = []
        for i in range(1, len(all_bars) + 1):
            window = all_bars.iloc[:i]
            for rule in self._rules:
                if rule.timeframe != timeframe:
                    continue
                sig = rule.evaluate(symbol, window)
                if sig is None:
                    continue
                dedup = sig.dedup_key()
                if dedup in self._seen:
                    continue
                self._seen.add(dedup)
                signals.append(sig)
        return signals
