"""Tests for the main monitor loop in `monitor.app`.

These exercise the *control flow* of `_run_market_session` — that it survives
session boundaries (day↔night, overnight, weekend) and only exits when the
stop signal is set. Real broker / scheduler interactions are stubbed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from monitor import app
from monitor.instruments import InstrumentType


def _make_settings():
    return SimpleNamespace(
        active_types=[InstrumentType.DOMESTIC_FUTURES],
        instruments={},
        symbols=[],
    )


@pytest.mark.asyncio
async def test_loop_survives_session_close(monkeypatch):
    """The loop must NOT exit just because the current session ends —
    it should sleep through the gap and resume on the next session."""
    stop_event = asyncio.Event()

    # Sequence of scheduler.any_in_session return values, simulating:
    #   open → open → close (gap) → open → open → stop
    in_session_seq = iter([True, True, False, True, True])

    def fake_any_in_session(types, dt=None):
        try:
            return next(in_session_seq)
        except StopIteration:
            return True

    # In the gap, claim the next session opens immediately so the test
    # doesn't actually wait.
    monkeypatch.setattr(app.scheduler, "any_in_session", fake_any_in_session)
    monkeypatch.setattr(app.scheduler, "seconds_until_next_open",
                        lambda types, dt=None: 0.0)
    monkeypatch.setattr(app, "_POLL_INTERVAL", 0.0)

    poll_calls = 0

    async def fake_poll(*args, **kwargs):
        nonlocal poll_calls
        poll_calls += 1
        if poll_calls >= 4:
            stop_event.set()

    monkeypatch.setattr(app, "_poll_once", fake_poll)

    await app._run_market_session(
        client=None, builder=None, engine=None, store=None,
        notifier=AsyncMock(),
        settings=_make_settings(),
        stop_event=stop_event,
    )

    # Polled before the gap (×2) AND after the gap (×2) — proves the loop
    # didn't terminate when the session closed.
    assert poll_calls >= 3, f"loop exited prematurely after {poll_calls} polls"


@pytest.mark.asyncio
async def test_loop_exits_on_stop_event(monkeypatch):
    """Setting stop_event must terminate the loop within one poll cycle,
    even when the market is wide open."""
    stop_event = asyncio.Event()

    monkeypatch.setattr(app.scheduler, "any_in_session",
                        lambda types, dt=None: True)
    monkeypatch.setattr(app, "_POLL_INTERVAL", 0.0)

    poll_calls = 0

    async def fake_poll(*args, **kwargs):
        nonlocal poll_calls
        poll_calls += 1
        stop_event.set()  # request stop after first poll

    monkeypatch.setattr(app, "_poll_once", fake_poll)

    await asyncio.wait_for(
        app._run_market_session(
            client=None, builder=None, engine=None, store=None,
            notifier=AsyncMock(),
            settings=_make_settings(),
            stop_event=stop_event,
        ),
        timeout=2.0,
    )

    assert poll_calls == 1


@pytest.mark.asyncio
async def test_loop_handles_no_upcoming_session(monkeypatch):
    """If `seconds_until_next_open` returns inf (no session within horizon),
    the loop must sleep and recheck — not exit."""
    stop_event = asyncio.Event()
    next_open_calls = 0

    def fake_next_open(types, dt=None):
        nonlocal next_open_calls
        next_open_calls += 1
        # First call: pretend no session in horizon. Second call: stop.
        if next_open_calls >= 2:
            stop_event.set()
        return float("inf")

    monkeypatch.setattr(app.scheduler, "any_in_session",
                        lambda types, dt=None: False)
    monkeypatch.setattr(app.scheduler, "seconds_until_next_open", fake_next_open)
    monkeypatch.setattr(app, "_IDLE_RECHECK_INTERVAL", 0.0)

    await asyncio.wait_for(
        app._run_market_session(
            client=None, builder=None, engine=None, store=None,
            notifier=AsyncMock(),
            settings=_make_settings(),
            stop_event=stop_event,
        ),
        timeout=2.0,
    )

    assert next_open_calls >= 2, "loop should recheck rather than exit on inf"
