from __future__ import annotations

import asyncio
import sys

from loguru import logger

from monitor.broker.shioaji_client import ShioajiClient
from monitor.config import load_settings
from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import load_history
from monitor.data.mock import make_mock_history
from monitor.indicators.compute import compute_last
from monitor.notify.telegram import TelegramNotifier

_DEMO_TFS = ["1m", "5m", "15m"]
_SEPARATOR = "─" * 44


def _fmt_tf(sym: str, tf: str, df) -> str:
    if df is None or df.empty:
        return f"  [{tf}] 無資料"

    last = df.index[-1]
    ts_str = last.strftime("%m/%d %H:%M") if hasattr(last, "strftime") else str(last)
    ind = compute_last(df)

    lines = [f"  [{tf}] {ts_str}  收:{df['close'].iloc[-1]:.2f}  量:{int(df['volume'].iloc[-1]):,}"]
    if ind:
        lines += [
            f"    MA5={ind['ma5']}  MA20={ind['ma20']}",
            f"    BB  上={ind['bb_upper']}  中={ind['bb_middle']}  下={ind['bb_lower']}",
            f"    KD  K={ind['kd_k']}  D={ind['kd_d']}",
            f"    MACD DIF={ind['macd_dif']}  DEM={ind['macd_dem']}  OSC={ind['macd_osc']}",
            f"    ATR14={ind['atr14']}",
        ]
    else:
        lines.append("    (K 棒不足 26 根，跳過指標)")
    return "\n".join(lines)


def _build_report(builder: BarBuilder, symbols: list[str]) -> str:
    blocks = ["TW stock monitor — M2 indicators demo"]
    for sym in symbols:
        blocks.append(f"\n{_SEPARATOR}\n  {sym}\n{_SEPARATOR}")
        for tf in _DEMO_TFS:
            df = builder.get_bars(sym, tf)
            blocks.append(_fmt_tf(sym, tf, df))
    return "\n".join(blocks)


def _telegram_summary(builder: BarBuilder, sym: str) -> str:
    """Compact single-symbol 5m snapshot for Telegram (≤ 4096 chars)."""
    df = builder.get_bars(sym, "5m")
    ind = compute_last(df) if df is not None and not df.empty else None

    if df is None or df.empty or ind is None:
        return f"M2 demo: {sym} — 無 5m 資料或 K 棒不足"

    last_ts = df.index[-1].strftime("%H:%M") if hasattr(df.index[-1], "strftime") else ""
    return (
        f"M2 indicators demo\n"
        f"{sym} 5m @ {last_ts}  收:{df['close'].iloc[-1]:.2f}\n"
        f"MA5={ind['ma5']}  MA20={ind['ma20']}\n"
        f"BB 上={ind['bb_upper']}  中={ind['bb_middle']}  下={ind['bb_lower']}\n"
        f"KD K={ind['kd_k']}  D={ind['kd_d']}\n"
        f"MACD DIF={ind['macd_dif']}  OSC={ind['macd_osc']}\n"
        f"ATR14={ind['atr14']}"
    )


async def _run(mock: bool = False) -> int:
    settings = load_settings()
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    if mock:
        logger.info("Mock mode: generating synthetic 30-day history (no Shioaji login)")
        hist = make_mock_history(settings.symbols, n_days=30)
    else:
        client = ShioajiClient(
            api_key=settings.shioaji_api_key,
            secret_key=settings.shioaji_secret_key,
            simulation=settings.shioaji_simulation,
        )
        client.login()
        try:
            hist = load_history(client, settings.symbols, lookback_days=60)
        finally:
            client.logout()

    if not hist:
        msg = "M2 demo: 無歷史資料 (非交易日/模擬資料空)"
        logger.error(msg)
        await notifier.send(msg)
        return 1

    builder = BarBuilder(hist)
    report = _build_report(builder, settings.symbols)
    print(report)

    first_sym = next(iter(hist))
    await notifier.send(_telegram_summary(builder, first_sym))
    return 0


def indicators_demo() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    mock = "--mock" in sys.argv
    sys.exit(asyncio.run(_run(mock=mock)))
