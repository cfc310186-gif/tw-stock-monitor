from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from monitor.data.store import SignalStore
from monitor.rules.base import Signal

_TZ = ZoneInfo("Asia/Taipei")


def _sig(symbol: str = "2330", rule: str = "bb_reversal_5m",
         tf: str = "5m", bar_ts: datetime | None = None) -> Signal:
    bar_ts = bar_ts or datetime(2024, 1, 2, 10, 5, tzinfo=_TZ)
    return Signal(
        symbol=symbol,
        rule_name=rule,
        timeframe=tf,
        bar_close_time=bar_ts,
        message="test signal",
    )


@pytest.fixture
def store(tmp_path):
    s = SignalStore(tmp_path / "test.db")
    yield s
    s.close()


def test_save_returns_true_for_new(store):
    assert store.save(_sig()) is True


def test_save_returns_false_for_duplicate(store):
    sig = _sig()
    store.save(sig)
    assert store.save(sig) is False


def test_save_different_bar_time_is_new(store):
    t1 = datetime(2024, 1, 2, 10, 5, tzinfo=_TZ)
    t2 = datetime(2024, 1, 2, 10, 10, tzinfo=_TZ)
    assert store.save(_sig(bar_ts=t1)) is True
    assert store.save(_sig(bar_ts=t2)) is True


def test_recent_dedup_keys_empty_initially(store):
    since = datetime.now(_TZ) - timedelta(hours=1)
    assert store.recent_dedup_keys(since) == set()


def test_recent_dedup_keys_after_save(store):
    now = datetime.now(_TZ)
    sig = _sig()
    store.save(sig, triggered_at=now)
    keys = store.recent_dedup_keys(now - timedelta(seconds=1))
    assert sig.dedup_key() in keys


def test_recent_dedup_keys_excludes_old(store):
    old_ts = datetime(2024, 1, 2, 10, 5, tzinfo=_TZ)
    sig = _sig(bar_ts=old_ts)
    store.save(sig, triggered_at=old_ts)
    # Query since "now" — should not include yesterday's signal
    keys = store.recent_dedup_keys(datetime.now(_TZ))
    assert sig.dedup_key() not in keys
