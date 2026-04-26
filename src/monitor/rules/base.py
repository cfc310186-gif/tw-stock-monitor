from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from monitor.instruments import InstrumentType


@dataclass
class Signal:
    symbol: str
    rule_name: str
    timeframe: str
    bar_close_time: datetime
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> tuple:
        return (self.symbol, self.rule_name, self.timeframe, self.bar_close_time)


class Rule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def timeframe(self) -> str: ...

    @property
    def cooldown_minutes(self) -> int:
        return 30

    @property
    def applies_to(self) -> set[InstrumentType]:
        """Which instrument types this rule should run on. Defaults to all
        types — concrete rules / YAML can narrow it down."""
        return set(InstrumentType)

    @abstractmethod
    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        """Return a Signal if the rule triggers on the last bar, else None."""
        ...

    @classmethod
    def from_config(cls, cfg: dict) -> "Rule":
        raise NotImplementedError(f"{cls.__name__} does not implement from_config")


def parse_applies_to(cfg: dict) -> set[InstrumentType]:
    """Parse a YAML rule's `applies_to` field into a set of InstrumentType.

    Accepts a single string or a list. If absent, the rule applies to all
    types (the default).
    """
    raw = cfg.get("applies_to")
    if raw is None:
        return set(InstrumentType)
    items = raw if isinstance(raw, list) else [raw]
    out: set[InstrumentType] = set()
    for it in items:
        try:
            out.add(InstrumentType(str(it)))
        except ValueError as exc:
            raise ValueError(
                f"Invalid applies_to '{it}'. Allowed: "
                + ", ".join(t.value for t in InstrumentType)
            ) from exc
    if not out:
        raise ValueError("applies_to may not be empty")
    return out
