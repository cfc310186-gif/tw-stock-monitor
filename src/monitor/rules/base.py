from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


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

    @abstractmethod
    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        """Return a Signal if the rule triggers on the last bar, else None."""
        ...

    @classmethod
    def from_config(cls, cfg: dict) -> "Rule":
        raise NotImplementedError(f"{cls.__name__} does not implement from_config")
