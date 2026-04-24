TW Intraday Stock Monitor — 完整規劃
0. 專案定位
在台股盤中（9:00–13:30），以永豐金 Shioaji API 為資料源，依據技術面 K 棒與量能指標即時監測自選池，觸發條件時透過 Telegram Bot 推送通知。

1. 確定需求
項目	內容
資料源	永豐金 Shioaji（已完成 API 簽署）
監測範圍	50–300 檔自選池
延遲容忍	20–60 秒
K 棒週期	1 分、5 分、15 分、30 分、60 分、日線
通知管道	Telegram Bot
執行環境	極簡起步（本機 / NAS），之後再視穩定度搬 VPS
實作語言	Python（Shioaji 只有 Python SDK）
Repo 策略	獨立 repo
2. 觸發條件大方向（可擴充）
已確認要支援的規則類型：

均線 / KD / MACD 等傳統指標
K 棒型態 / 價格型態
布林通道反轉（前一根收在軌道外 → 當根「豬羊變色」收回軌道內）
「豬羊變色」定義：與前一根 K 棒顏色相反（前黑這紅，或前紅這黑）。

規則設計為可插拔 YAML 配置，之後陸續補：

5MA/20MA 黃金交叉後的反轉 K 棒
突破盤整區間（Donchian squeeze + 突破）
其他自訂組合
3. 資料來源盤點（備忘）
層級	管道	定位
首選	Shioaji	本專案主要資料源
備援	Fugle 行情 API	若日後遷移或做 cross-check
輔助	TWSE OpenAPI	盤後日頻資料、回測用
參考	Fubon Neo、FinMind	同類替代方案
4. 系統架構
┌─────────────────────────────────────────────────────────────┐
│  配置層：watchlist.yaml、rules.yaml、.env                    │
└─────────────────────────────────────────────────────────────┘
           │
 ┌─────────▼─────────┐     ┌──────────────┐
 │  Shioaji Client   │────▶│ Bar Builder  │  聚合 snapshot/tick
 │  (snapshot poll   │     │ 1/5/15/30/60 │  → 各週期 K 棒
 │   or WS)          │     │ 分 + 日線     │
 └─────────┬─────────┘     └──────┬───────┘
           │ 盤前載入                │
 ┌─────────▼─────────┐              │
 │ Historical Loader │  歷史 K 棒    │
 │ (api.kbars)       ├──────────────┤  bootstrap 指標
 └───────────────────┘              │
                                    │
                          ┌─────────▼────────┐
                          │ Indicator Cache  │  MA/EMA/KD/MACD/
                          │ (symbol×tf)      │  BBANDS/ATR/Donchian
                          └─────────┬────────┘
                                    │
                          ┌─────────▼────────┐
                          │  Rule Engine     │  可插拔規則
                          │  (AND/OR/score)  │  冷卻/去重
                          └─────────┬────────┘
                                    │ 觸發
                          ┌─────────▼────────┐
                          │ Notifier         │  Telegram
                          │ + Signal Store   │  SQLite 紀錄
                          └──────────────────┘
5. 目錄結構
tw-stock-monitor/
├── pyproject.toml
├── .gitignore
├── config/
│   ├── watchlist.yaml          # 自選池
│   ├── rules.yaml              # 規則組合
│   └── .env.example            # Shioaji / Telegram 憑證樣板
├── src/monitor/
│   ├── __init__.py
│   ├── app.py                  # asyncio entrypoint
│   ├── config.py               # 載 yaml + .env
│   ├── scheduler.py            # 交易日 / 開收盤判斷
│   ├── broker/
│   │   ├── __init__.py
│   │   └── shioaji_client.py   # 連線、重連、snapshot、訂閱
│   ├── data/
│   │   ├── bar_builder.py      # snapshot / tick → K 棒
│   │   ├── historical.py       # 盤前載入歷史 K
│   │   └── store.py            # SQLite 持久化 + 訊號紀錄
│   ├── indicators/
│   │   ├── ma.py
│   │   ├── kd.py
│   │   ├── macd.py
│   │   ├── bbands.py
│   │   ├── donchian.py
│   │   └── registry.py         # 指標註冊表
│   ├── rules/
│   │   ├── base.py             # Rule 基底
│   │   ├── engine.py           # 規則引擎 + 冷卻 + 去重
│   │   ├── bb_reversal.py      # 布林軌道外反轉 + 豬羊變色
│   │   ├── ma_cross_reversal.py
│   │   └── range_breakout.py
│   └── notify/
│       └── telegram.py
├── tests/
│   └── （每個指標 / 規則都有單元測試）
├── backtest/
│   └── runner.py               # 歷史回放
└── docker/
    ├── Dockerfile
    └── compose.yml
6. 技術棧
類別	選擇	備註
語言	Python 3.10+	Shioaji 相容性
券商 SDK	shioaji	永豐金官方
技術指標	pandas + pandas-ta（或 TA-Lib）	指標計算
通知	python-telegram-bot	v21+ async
配置	pyyaml + python-dotenv	
Log	loguru	
並發	asyncio	單行程 event loop
持久化	sqlite3（或 duckdb）	K 棒快取、訊號紀錄
測試	pytest + pytest-asyncio	
Lint	ruff	
7. 關鍵技術決策
7.1 Shioaji 訂閱策略（50–300 檔）
起步（M1–M4）：api.snapshots() 每 15–30 秒輪詢 —— 穩定、除錯容易、完全滿足 60 秒延遲需求
進階（之後）：如需秒級觸發再切換 api.quote.subscribe(bidask/quote)
不建議 300 檔全部訂 tick —— 容易撞連線上限
7.2 K 棒收盤確認
預設策略：K 棒收盤才評估規則（例：5 分 K 在 09:05、09:10… 收盤時檢查）
目的：避免訊號閃爍（剛觸發 → 下一秒又不滿足）
日線例外：用「前一日收盤 + 今日最新 snapshot」算盤中日線指標
7.3 Bootstrap（歷史 K 載入）
啟動時呼叫 api.kbars(contract, start, end) 抓取足夠天數（例如 60 個交易日）
盤中新 K 收盤後 append 到滾動視窗
7.4 去重與冷卻
唯一鍵：(symbol, rule_name, timeframe, bar_close_time) —— 同一根 K 只觸發一次
每條規則可設 cooldown_minutes —— 同檔 N 分鐘內不重複
全域：同一檔 10 分鐘內最多 1 則通知（避免多規則同時轟炸）
7.5 量能處理
盤中量比：當日累計量 ÷ 過去 N 日同時段累計量
單根 K 量：該根量 ÷ 近 20 根同週期均量
7.6 集合競價處理
9:00 前、13:25–13:30 的資料特性不同 → 排除或標記 is_auction=true
非交易日自動休眠
7.7 同一 API key 同時只能一個 session
本機測試時上雲前要先下線，否則會互踢
8. 規則引擎 YAML 格式
- name: bb_reversal_5m
  enabled: true
  timeframe: 5m
  logic: AND
  conditions:
    - type: bb_outside_prev          # 前一根收在布林軌道外
      side: lower                    # lower | upper
      period: 20
      stddev: 2
    - type: candle_color_flip        # 豬羊變色（前黑這紅 或 前紅這黑）
    - type: close_inside_bb          # 當根收回軌道內
      period: 20
      stddev: 2
  cooldown_minutes: 30

- name: ma_cross_reversal_5m
  enabled: true
  timeframe: 5m
  conditions:
    - type: ma_cross
      fast: 5
      slow: 20
      direction: golden              # golden | death
      within_bars: 3                 # 3 根 K 內剛發生交叉
    - type: candle_reversal          # 錘頭 / 吞噬 / 豬羊變色
  cooldown_minutes: 30

- name: range_breakout_15m
  enabled: true
  timeframe: 15m
  conditions:
    - type: donchian_squeeze         # 前 N 根高低收斂
      lookback: 20
      threshold_atr: 1.0
    - type: close_above_range_high
      lookback: 20
    - type: volume_ratio
      base: avg_20                   # 相對近 20 根均量
      multiplier: 1.5
  cooldown_minutes: 60
9. Telegram 訊息格式
📈 bb_reversal_5m 觸發
2330 台積電 5分K @ 10:15
收盤 1145 (+0.88%)
布林下軌外反轉回軌道內｜豬羊變色紅K
量 8,234 張（量比 1.8x）
10. 里程碑
階段	目標	驗收標準
M1 連線打通	Shioaji 登入 + snapshot + Telegram 發訊息	盤中執行能看到 5 檔報價，手機收到 Telegram
M2 K 棒 + 指標	1/5 分 K 聚合；MA/BB/KD/MACD/Donchian 計算	指標值與看盤軟體對齊；pytest 全綠
M3 規則引擎	載 rules.yaml；實作 bb_reversal 作為 reference	歷史 K 回放訊號數合理
M4 盤中實戰	scheduler + 冷卻 + SQLite；Docker 化	連跑一週無斷線、無重複通知
M5 擴充規則	MA 交叉反轉、區間突破、自訂組合	新增規則只動 YAML + 一個 rule 檔
M6 回測	歷史回放器 + 命中率統計	每條規則有歷史績效報告
11. 部署
極簡起步（M1–M3）
本機 monitor 指令直接跑
或 python -m monitor.app
穩定運行（M4+）
docker compose up -d
restart: unless-stopped
內建交易日判斷：非交易日 sleep、09:00 前 bootstrap、13:30 後停止訂閱
Log：loguru 寫 rotating file + stdout
備援：Telegram Bot 加 /status 指令查連線狀態、訂閱數、當日訊號數
之後要搬 VPS
Docker image 直接拉走，推薦：

GCP e2-micro（永久免費）
Linode / Vultr $5/月
12. 風險注意事項
Shioaji WebSocket 斷線 → exponential backoff 重連 + 重新訂閱
同檔多策略訊號轟炸 → per-symbol 全域冷卻
集合競價資料 → 排除或標記
興櫃 / 零股混進來 → watchlist 限制 TSE/OTC 上市上櫃
API key 單 session 限制 → 本機測試與雲端擇一跑
永豐金 API 限速 → snapshot 輪詢間隔 ≥ 15 秒，300 檔建議分批 call
13. M1 骨架檔案內容（可直接重建）
pyproject.toml
[project]
name = "tw-stock-monitor"
version = "0.1.0"
description = "Intraday TW stock monitor that triggers Telegram alerts on technical + volume rules."
requires-python = ">=3.10"
dependencies = [
  "shioaji>=1.2",
  "python-telegram-bot>=21",
  "pyyaml>=6",
  "python-dotenv>=1",
  "loguru>=0.7",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]

[project.scripts]
monitor = "monitor.app:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"
.gitignore
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.env
config/.env
*.log
dist/
build/
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/
config/watchlist.yaml
symbols:
  - "2330"
  - "2317"
  - "2454"
  - "0050"
  - "2603"
config/.env.example
SHIOAJI_API_KEY=
SHIOAJI_SECRET_KEY=
SHIOAJI_CA_PATH=
SHIOAJI_CA_PASSWORD=
SHIOAJI_PERSON_ID=
SHIOAJI_SIMULATION=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
src/monitor/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    shioaji_api_key: str
    shioaji_secret_key: str
    shioaji_ca_path: str | None
    shioaji_ca_password: str | None
    shioaji_person_id: str | None
    shioaji_simulation: bool
    telegram_bot_token: str
    telegram_chat_id: str
    symbols: list[str]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def load_settings(config_dir: Path | str = "config") -> Settings:
    config_dir = Path(config_dir)

    env_path = config_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    watchlist_path = config_dir / "watchlist.yaml"
    watchlist = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    symbols = [str(s) for s in watchlist.get("symbols", [])]
    if not symbols:
        raise RuntimeError(f"No symbols found in {watchlist_path}")

    return Settings(
        shioaji_api_key=_required("SHIOAJI_API_KEY"),
        shioaji_secret_key=_required("SHIOAJI_SECRET_KEY"),
        shioaji_ca_path=_optional("SHIOAJI_CA_PATH"),
        shioaji_ca_password=_optional("SHIOAJI_CA_PASSWORD"),
        shioaji_person_id=_optional("SHIOAJI_PERSON_ID"),
        shioaji_simulation=os.environ.get("SHIOAJI_SIMULATION", "false").lower() == "true",
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
        symbols=symbols,
    )
src/monitor/broker/shioaji_client.py
from __future__ import annotations

from dataclasses import dataclass

import shioaji as sj
from loguru import logger


@dataclass(frozen=True)
class SnapshotRow:
    code: str
    name: str
    close: float
    change_price: float
    change_rate: float
    total_volume: int


class ShioajiClient:
    def __init__(self, api_key: str, secret_key: str, simulation: bool = False) -> None:
        self._api = sj.Shioaji(simulation=simulation)
        self._api_key = api_key
        self._secret_key = secret_key
        self._simulation = simulation

    def login(self) -> None:
        logger.info("Shioaji login (simulation={})", self._simulation)
        self._api.login(api_key=self._api_key, secret_key=self._secret_key)
        logger.info("Shioaji login OK")

    def logout(self) -> None:
        try:
            self._api.logout()
        except Exception as exc:
            logger.warning("Shioaji logout failed: {}", exc)

    def snapshots(self, symbols: list[str]) -> list[SnapshotRow]:
        contracts = []
        name_by_code: dict[str, str] = {}
        for sym in symbols:
            contract = self._api.Contracts.Stocks[sym]
            if contract is None:
                logger.warning("Unknown symbol, skipped: {}", sym)
                continue
            contracts.append(contract)
            name_by_code[contract.code] = contract.name

        if not contracts:
            return []

        raw = self._api.snapshots(contracts)
        rows: list[SnapshotRow] = []
        for s in raw:
            rows.append(
                SnapshotRow(
                    code=s.code,
                    name=name_by_code.get(s.code, ""),
                    close=float(s.close),
                    change_price=float(s.change_price),
                    change_rate=float(s.change_rate),
                    total_volume=int(s.total_volume),
                )
            )
        return rows
src/monitor/notify/telegram.py
from __future__ import annotations

from loguru import logger
from telegram import Bot


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        preview = text.replace("\n", " | ")
        logger.debug("Telegram send: {}", preview)
        await self._bot.send_message(chat_id=self._chat_id, text=text)
src/monitor/app.py
from __future__ import annotations

import asyncio
import sys

from loguru import logger

from monitor.broker.shioaji_client import ShioajiClient, SnapshotRow
from monitor.config import load_settings
from monitor.notify.telegram import TelegramNotifier


def format_snapshots(rows: list[SnapshotRow]) -> str:
    lines = ["TW stock monitor — M1 smoke test", ""]
    for r in rows:
        sign = "+" if r.change_price >= 0 else ""
        lines.append(
            f"{r.code} {r.name}  {r.close:>8.2f}  "
            f"{sign}{r.change_price:.2f} ({sign}{r.change_rate:.2f}%)  "
            f"vol {r.total_volume:,}"
        )
    return "\n".join(lines)


async def _run() -> int:
    settings = load_settings()

    client = ShioajiClient(
        api_key=settings.shioaji_api_key,
        secret_key=settings.shioaji_secret_key,
        simulation=settings.shioaji_simulation,
    )
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    client.login()
    try:
        rows = client.snapshots(settings.symbols)
    finally:
        client.logout()

    if not rows:
        logger.error("No snapshots returned; check symbols / market hours")
        await notifier.send("M1 smoke test: no snapshot rows returned")
        return 1

    message = format_snapshots(rows)
    print(message)
    await notifier.send(message)
    return 0


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
tests/test_smoke.py
from monitor.app import format_snapshots
from monitor.broker.shioaji_client import SnapshotRow


def test_format_snapshots_renders_row():
    rows = [
        SnapshotRow(
            code="2330",
            name="台積電",
            close=1145.0,
            change_price=10.0,
            change_rate=0.88,
            total_volume=23456,
        )
    ]
    out = format_snapshots(rows)
    assert "2330" in out
    assert "台積電" in out
    assert "1145.00" in out
    assert "+10.00" in out
    assert "+0.88%" in out
    assert "23,456" in out


def test_format_snapshots_negative_change():
    rows = [
        SnapshotRow(
            code="2317",
            name="鴻海",
            close=200.0,
            change_price=-1.5,
            change_rate=-0.74,
            total_volume=10000,
        )
    ]
    out = format_snapshots(rows)
    assert "-1.50" in out
    assert "-0.74%" in out
空檔案（建立 Python package 用）
src/monitor/__init__.py
src/monitor/broker/__init__.py
src/monitor/notify/__init__.py
tests/__init__.py
14. 本機驗收步驟（M1）
cd tw-stock-monitor
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cp config/.env.example config/.env
# 編輯 config/.env：
#   SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY → 永豐 API 後台
#   TELEGRAM_BOT_TOKEN → @BotFather 建 Bot
#   TELEGRAM_CHAT_ID → 跟 Bot 傳訊息後看
#     https://api.telegram.org/bot<TOKEN>/getUpdates 的 chat.id

pytest                                # 不用憑證即可跑
monitor                               # 盤中 9:00–13:30 實跑
驗收標準：終端看到 5 檔報價 + 手機 Telegram 收到相同訊息。
