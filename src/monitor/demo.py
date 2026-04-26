from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

from monitor.broker.shioaji_client import ShioajiClient
from monitor.config import load_settings
from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import load_history
from monitor.data.mock import make_mock_history
from monitor.indicators.compute import compute_last
from monitor.notify.telegram import TelegramNotifier
from monitor.rules.engine import RuleEngine

_DEMO_TFS = ["1m", "5m", "15m"]
_SEPARATOR = "─" * 44
_RULES_YAML = Path(__file__).parent.parent.parent / "config" / "rules.yaml"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

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


def _build_indicator_report(builder: BarBuilder, symbols: list[str]) -> str:
    blocks = ["TW stock monitor — M2/M3 demo"]
    for sym in symbols:
        blocks.append(f"\n{_SEPARATOR}\n  {sym}\n{_SEPARATOR}")
        for tf in _DEMO_TFS:
            df = builder.get_bars(sym, tf)
            blocks.append(_fmt_tf(sym, tf, df))
    return "\n".join(blocks)


def _build_signal_report(hist: dict, engine: RuleEngine) -> str:
    lines = [f"\n{'═' * 44}", "  M3 規則回放結果", f"{'═' * 44}"]
    total = 0
    for sym, frames in hist.items():
        sym_sigs: list[str] = []
        for tf in ("5m", "15m"):
            df = frames.get(tf)
            if df is None or df.empty:
                continue
            signals = engine.replay(sym, tf, df)
            for sig in signals:
                ts = sig.bar_close_time
                ts_str = ts.strftime("%m/%d %H:%M") if hasattr(ts, "strftime") else str(ts)
                sym_sigs.append(f"  [{ts_str}] {sig.rule_name}  {sym} {tf}  收:{sig.details.get('close','?')}")
                total += 1
        if sym_sigs:
            lines.append(f"\n  {sym}")
            lines.extend(sym_sigs)
    lines.append(f"\n  合計 {total} 個訊號")
    return "\n".join(lines)


def _telegram_summary(builder: BarBuilder, sym: str, signals: list) -> str:
    df = builder.get_bars(sym, "5m")
    ind = compute_last(df) if df is not None and not df.empty else None

    ind_part = "（K 棒不足）"
    if ind:
        last_ts = df.index[-1].strftime("%H:%M") if hasattr(df.index[-1], "strftime") else ""
        ind_part = (
            f"5m @ {last_ts}  收:{df['close'].iloc[-1]:.2f}\n"
            f"MA5={ind['ma5']}  MA20={ind['ma20']}\n"
            f"BB 上={ind['bb_upper']}  中={ind['bb_middle']}  下={ind['bb_lower']}\n"
            f"KD K={ind['kd_k']}  D={ind['kd_d']}\n"
            f"MACD DIF={ind['macd_dif']}  OSC={ind['macd_osc']}"
        )

    sig_part = f"\n[M3] 回放共 {len(signals)} 個訊號"
    if signals:
        latest = signals[-1]
        ts = latest.bar_close_time
        ts_str = ts.strftime("%m/%d %H:%M") if hasattr(ts, "strftime") else str(ts)
        sig_part += f"\n最近: {latest.rule_name} @ {ts_str}"

    return f"M2/M3 demo — {sym}\n{ind_part}{sig_part}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _run(mock: bool = False) -> int:
    settings = load_settings()
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    if mock:
        logger.info("Mock mode: synthetic 30-day history (no Shioaji login)")
        hist = make_mock_history(settings.instruments, n_days=30)
    else:
        client = ShioajiClient(
            api_key=settings.shioaji_api_key,
            secret_key=settings.shioaji_secret_key,
            simulation=settings.shioaji_simulation,
        )
        client.login()
        try:
            hist = load_history(client, settings.instruments, lookback_days=60)
        finally:
            client.logout()

    if not hist:
        msg = "demo: 無歷史資料 (非交易日/模擬資料空)"
        logger.error(msg)
        await notifier.send(msg)
        return 1

    builder = BarBuilder(hist)

    # --- M2: indicator report ---
    print(_build_indicator_report(builder, settings.symbols))

    # --- M3: rule replay ---
    if _RULES_YAML.exists():
        engine = RuleEngine.from_yaml(_RULES_YAML)
        print(_build_signal_report(hist, engine))

        # collect all signals across symbols for Telegram summary
        all_signals: list = []
        for sym, frames in hist.items():
            engine2 = RuleEngine.from_yaml(_RULES_YAML)  # fresh engine per symbol
            df5 = frames.get("5m")
            if df5 is not None and not df5.empty:
                all_signals.extend(engine2.replay(sym, "5m", df5))
    else:
        logger.warning("config/rules.yaml not found, skipping rule replay")
        all_signals = []

    first_sym = next(iter(hist))
    await notifier.send(_telegram_summary(builder, first_sym, all_signals))
    return 0


def indicators_demo() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    mock = "--mock" in sys.argv
    sys.exit(asyncio.run(_run(mock=mock)))
