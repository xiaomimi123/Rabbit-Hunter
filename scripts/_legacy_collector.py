"""
⚠️  DEPRECATED (v45) — 已归档，仅供考古查阅，不再维护

  本文件原为 scripts/collector.py，是 Rabbit Hunter 第一版完整的"采集 + 主循环"实现，
  共 2670 行，直接写 Supabase。

  v45 起被 scripts.tasks.collector_main 取代（模块化 scanner / deep_collector /
  scorer / writer 四任务，写本机 SQLite）。

  本文件保留是为了：
    1) 历史追溯（git log 找原始实现）
    2) 偶尔参考某段旧逻辑（例如 ai_learning_loop 的内嵌线程模型）

  不要在此文件做任何 bug 修复 — 修了也没人会执行它。
  所有新代码请只改 scripts/tasks/ 下的模块。

──────────────────────────────────────────────────────────────────────────────

Rabbit Hunter - 全市场异动扫描器（三层漏斗筛选系统）

目标：
- 第一层（粗筛）：1秒扫描全市场，找出价格/成交量异动的 TOP 10
- 第二层（精筛）：对 TOP 10 做深度采集（OI、费率、LS Ratio）
- 第三层（存储）：只存异动币种 + Whale Alert 触发币种，不存平庸数据

运行前准备：
- 安装依赖：
    pip install ccxt supabase python-dotenv
- 在项目根目录创建 .env（或自行设置环境变量）：
    SUPABASE_URL=...
    SUPABASE_KEY=...      # 建议使用 service_role（仅在后端环境）
    BINANCE_API_KEY=...   # 可选，只读行情可以不配
    BINANCE_API_SECRET=...
"""

import os
import asyncio
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any

import ccxt
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

# 导入本地模块
# 由于脚本在 scripts/ 目录下运行，需要将 scripts 目录添加到路径
import sys
from pathlib import Path
_scripts_dir = Path(__file__).parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

try:
    from cvd_analyzer import CVDAnalyzer
except ImportError as e:
    print(f"[WARNING] 无法导入 CVDAnalyzer: {e}")
    # 如果导入失败，创建一个占位类
    class CVDAnalyzer:
        def __init__(self, *args, **kwargs):
            pass
        async def calculate_cvd_metrics(self, *args, **kwargs):
            return None

# V4.2 strategy_engine 已废弃，不再导入
# V4.3 使用新的打分系统，不再需要 strategy_engine
def generate_trade_signal(*args, **kwargs):
    """占位函数（V4.2 已废弃，V4.3 使用新的打分系统）"""
    return None, None, "V4.2 策略引擎已废弃，使用 V4.3 打分系统"

# V4.3 模块导入
try:
    from v43_feature_extractor import extract_features
    from v43_score_calculator import aggregate_score
    from v43_hard_filters import pass_hard_filters
    from v43_decision_policy import decision_policy, detect_market_regime, get_account_stage
    from v43_weight_manager import load_weights, DEFAULT_WEIGHTS
    from v43_chandelier_stop import initialize_position, update_chandelier_stop, should_exit_position
    from v43_position_manager import V43PositionManager
    V43_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] V4.3 模块导入失败: {e}")
    V43_AVAILABLE = False
    V43PositionManager = None  # type: ignore
    # 创建占位函数
    def extract_features(*args, **kwargs):
        return {}
    def aggregate_score(*args, **kwargs):
        return {"final_score": 0.0, "block_reason": "V4.3 模块未加载"}
    def pass_hard_filters(*args, **kwargs):
        return (False, "V4.3 模块未加载")
    def decision_policy(*args, **kwargs):
        return {"should_trade": False, "reason": "V4.3 模块未加载"}
    def detect_market_regime(*args, **kwargs):
        return "UNCERTAIN"
    def get_account_stage(*args, **kwargs):
        return "CONSERVATIVE"
    def load_weights(*args, **kwargs):
        return DEFAULT_WEIGHTS
    def initialize_position(*args, **kwargs):
        return {}
    def update_chandelier_stop(*args, **kwargs):
        return {}
    def should_exit_position(*args, **kwargs):
        return (False, "")

# AI Judge（可选）：模型文件不存在时自动跳过
try:
    from ai_judge import AIJudge
except Exception:  # noqa: BLE001
    AIJudge = None  # type: ignore

# DeepSeek AI（可选）：优先用 deepseek-chat 做“裁决”，失败回退本地模型
try:
    from deepseek_ai import DeepSeekJudge
except Exception:  # noqa: BLE001
    DeepSeekJudge = None  # type: ignore


# 载入根目录下的 .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 可选：只读公共行情不一定需要 key，但建议配置，方便后续下单/私有接口扩展
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")

# AI Judge 配置（可选）
AI_JUDGE_ENABLED = os.environ.get("AI_JUDGE_ENABLED", "1") not in ("0", "false", "False")
AI_JUDGE_THRESHOLD = float(os.environ.get("AI_JUDGE_THRESHOLD", "0.65"))

# DeepSeek 配置（默认使用 deepseek-chat）
DEEPSEEK_ENABLED = os.environ.get("DEEPSEEK_ENABLED", "0") in ("1", "true", "True")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_CACHE_SECONDS = int(os.environ.get("DEEPSEEK_CACHE_SECONDS", "60"))

# P3a 模式匹配（MVP）
P3A_MATCH_ENABLED = os.environ.get("P3A_MATCH_ENABLED", "1") in ("1", "true", "True")
P3A_MATCH_DAYS = int(os.environ.get("P3A_MATCH_DAYS", "14"))
P3A_MATCH_MIN_SAMPLES = int(os.environ.get("P3A_MATCH_MIN_SAMPLES", "50"))

# 动态阈值（MVP）：在"自信度更高"时抬升阈值，压制过度自信
AI_DYNAMIC_THRESHOLD_ENABLED = os.environ.get("AI_DYNAMIC_THRESHOLD_ENABLED", "1") in ("1", "true", "True")
AI_DYNAMIC_THRESHOLD_MAX_BOOST = float(os.environ.get("AI_DYNAMIC_THRESHOLD_MAX_BOOST", "0.20"))  # 最多 +0.20

# V4.3 配置
V43_ENABLED = os.environ.get("V43_ENABLED", "1") in ("1", "true", "True")  # 默认启用
V43_TRADE_THRESHOLD = float(os.environ.get("V43_TRADE_THRESHOLD", "0.65"))  # 交易阈值

# 三层漏斗筛选配置
SCAN_INTERVAL_SECONDS = 1        # 第一层：每 1 秒扫描全市场
DEEP_SCAN_INTERVAL_SECONDS = 60  # 第二层：每 60 秒对异动币种做深度采集

# CVD 计算频率（秒）——与第二层节奏对齐，避免过度调用 fetch_trades
CVD_UPDATE_INTERVAL_SECONDS = 60

# 异动筛选阈值
MIN_VOLUME_24H = 10_000_000    # 最小 24h 成交量（USDT）：1000万
MIN_PRICE_CHANGE_5M = 2.0       # 5分钟涨幅阈值：2%
VOLUME_SPIKE_MULTIPLIER = 3.0  # 成交量倍数：当前是过去均值的 3 倍
TOP_MOVERS_COUNT = 10           # 第一层筛选出的 TOP 异动币种数量

# 可选：过滤“极端暴跌”的币（避免垃圾堆噪音）
# 例如设置为 -20：将剔除 24h 跌幅 <= -20% 的币
_skip_drop_raw = os.environ.get("SKIP_24H_DROP_PCT", "").strip()
SKIP_24H_DROP_PCT: float | None = None
if _skip_drop_raw:
    try:
        SKIP_24H_DROP_PCT = float(_skip_drop_raw)
    except Exception:
        SKIP_24H_DROP_PCT = None

# 存储策略：只存 Top 异动币种 + Whale Alert 触发币种
STORE_TOP_COUNT = 10            # 存 Top N 异动币种到 ai_training_data（会触发 AI 裁决与训练数据沉淀）

# Supabase 写入队列（避免写库阻塞采集）
WRITE_QUEUE_MAXSIZE = 300
WRITE_WORKERS = 1  # supabase-py 为阻塞客户端，单 worker 足够，避免并发过大引发抖动/限流


def compute_v4_snapshot(
    *,
    market_phase: str | None,
    kill_zone_signal: str | None,
    exit_clarity_score: int | None,
    funding_rate: float,
    confidence_level: int | None,
    ls_ratio: float | None,
) -> tuple[str, list[str], int]:
    """
    V4 版本：生成用于前端展示的 snapshot 信息（market_snapshot + ai_training_data 的展示字段）。

    注意：
    - 这里的 risk_score 不再用于“禁止交易”，仅用于 UI 排序/可视化。
    - 旧字段名（market_regime/risk_score/risk_reasons）保留是为了前端兼容。
    """
    reasons: list[str] = []
    kz = (kill_zone_signal or "NONE").upper()
    phase = market_phase or "UNKNOWN"
    exit_score = int(exit_clarity_score) if exit_clarity_score is not None else 0

    # market_regime（写库兼容 V2 enum）：
    # - DB enum: NORMAL/TREND_UP/TREND_DOWN/SQUEEZE/MANIPULATED/LOW_LIQ/CROWDED_LONG
    # - V4 详情用 market_phase/kill_zone_signal 字段表达；这里仅做“兼容映射”
    def _to_db_regime(kz_: str, phase_: str) -> str:
        kz_u = (kz_ or "NONE").upper()
        ph_u = (phase_ or "UNKNOWN").upper()
        if kz_u in ("SQUEEZE", "SHORT_SQUEEZE"):
            return "SQUEEZE"
        if kz_u in ("SHAKEOUT", "ACCUMULATION"):
            return "MANIPULATED"
        if ph_u in ("P3A_PUMP_START", "P3B_PUMP_LATE"):
            return "TREND_UP"
        if ph_u in ("P4_DISTRIBUTION",):
            return "TREND_DOWN"
        # P1/P2/UNKNOWN 等都视为 NORMAL（不再用 UNKNOWN 写库，避免 enum 报错）
        return "NORMAL"

    regime = _to_db_regime(kz, phase)
    if kz in ("SQUEEZE", "ACCUMULATION", "SHAKEOUT"):
        reasons.append(f"KZ_{kz}")
    else:
        reasons.append(f"PHASE_{phase}")

    # risk_score（UI 用）：机会越“剧烈/极端”，分越高；退出越清晰，分适度下调
    score = 20
    if kz == "SQUEEZE":
        score = 92
    elif kz == "SHAKEOUT":
        score = 78
    elif kz == "ACCUMULATION":
        score = 55
    elif phase == "P3A_PUMP_START":
        score = 70
    elif phase in ("P3B_PUMP_LATE", "P4_DISTRIBUTION"):
        score = 85
    elif phase == "P1_NO_WHALE":
        score = 25

    # funding 极端：提高“剧烈度”评分
    if funding_rate < -0.0005:
        reasons.append("NEGATIVE_FUNDING")
        score = max(score, 90)

    # 退出越清晰，风险表现下调（但不低于 10）
    score = max(10, min(100, score - int(exit_score / 10)))

    # 反身性刹车：confidence_level 高 -> 标记
    if confidence_level is not None and confidence_level >= 80:
        reasons.append("ANTI_CONFIDENCE_BRAKE")
        score = min(100, score + 5)

    # 多空比（散户拥挤）仅作为提示，不再决定交易
    if ls_ratio is not None and float(ls_ratio) > 2.5:
        reasons.append("HIGH_LS_RATIO")
        score = min(100, score + 5)

    return regime, reasons, int(score)


def init_supabase() -> Client | None:
    """初始化 Supabase 客户端。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[WARNING] 未配置 SUPABASE_URL / SUPABASE_KEY，将只打印数据，不写入数据库。")
        return None

    # 先做 URL 可达性检查，避免“URL 写错导致 404 空响应 -> JSON could not be generated”
    try:
        health_url = SUPABASE_URL.rstrip("/") + "/auth/v1/health"
        r = requests.get(health_url, timeout=10)
        # 说明：
        # - 200：健康
        # - 401/403：多数情况下是“没带 key/没权限”，但 URL 是通的（可继续用 client 走 PostgREST 连接测试）
        # - 404：通常是 URL/路径错误
        if r.status_code not in (200, 401, 403):
            print(f"[ERROR] Supabase URL 可能不正确：GET {health_url} -> {r.status_code}")
            print("[INFO] 正确的 SUPABASE_URL 应类似：https://<project_ref>.supabase.co")
            print("[WARNING] 将只打印数据，不写入数据库。")
            return None
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Supabase URL 健康检查失败：{e}")
        print("[INFO] 请检查网络/VPN，以及 SUPABASE_URL 是否为 https://<project_ref>.supabase.co")
        print("[WARNING] 将只打印数据，不写入数据库。")
        return None

    # 检查 key 类型
    if SUPABASE_KEY.startswith("sbp_"):
        print(
            "[ERROR] 检测到 SUPABASE_KEY 以 sbp_ 开头（Personal Access Token），"
            "supabase-py 无法用它读写数据表。"
        )
        print("[INFO] 请使用以下任一类型的 key：")
        print("       1. 新版本：Secret key (sb_secret_... 开头)")
        print("       2. 旧版本：service_role key (eyJ... 开头的 JWT)")
        print("[INFO] 获取方式：Supabase Dashboard -> Settings -> API")
        return None
    
    # 检查是否是新版本的 secret key 或旧版本的 JWT key
    if SUPABASE_KEY.startswith("sb_secret_"):
        print("[INFO] 检测到新版本 Secret key (sb_secret_ 开头)")
        print("[WARNING] 注意：新版本 key 可能不被当前 supabase-py 支持")
        print("[INFO] 如果连接失败，建议使用 Legacy service_role key")
    elif SUPABASE_KEY.startswith("eyJ"):
        print("[INFO] 检测到旧版本 service_role key (JWT 格式)")
    else:
        print(f"[WARNING] 未知的 API key 格式，尝试连接...")

    try:
        client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # 直接测试数据库连接（查询表）
        # 先尝试查询 ai_training_data（核心表，必须存在）
        try:
            test_response = client.table("ai_training_data").select("id").limit(1).execute()
        except Exception as e1:  # noqa: BLE001
            # 如果核心表也查不到，说明连接有问题
            raise e1
        
        # 再测试 system_settings（可选表，如果不存在会创建）
        try:
            test_response = client.table("system_settings").select("key").limit(1).execute()
        except Exception as e2:  # noqa: BLE001
            # system_settings 表不存在不影响主流程，只打印警告
            if "PGRST205" in str(e2) or "Could not find the table" in str(e2):
                print(f"[WARNING] system_settings 表不存在，但不影响数据采集（将在首次使用时自动创建）")
            else:
                raise e2
        
        print("[INFO] Supabase 连接成功！可以正常读写数据。")
        return client
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        print(f"[ERROR] Supabase 连接失败: {e}")
        
        # 提供更详细的错误诊断
        if "404" in msg or "JSON could not be generated" in msg:
            print("[INFO] 可能的原因：")
            print("       1. SUPABASE_URL 不正确（应类似：https://<project_ref>.supabase.co）")
            print("       2. 新版本的 sb_secret_ key 可能不被 supabase-py 支持")
            print("[INFO] 建议：尝试使用 Legacy service_role key（eyJ... 开头的 JWT）")
            print("       获取方式：Supabase Dashboard -> Settings -> API -> Legacy anon, service_role API keys")
        elif "401" in msg or "403" in msg or "permission" in msg.lower():
            print("[INFO] 可能的原因：")
            print("       1. API key 无效或已过期")
            print("       2. 使用了 Publishable key（需要 Secret key 或 service_role）")
            print("       3. 新版本的 sb_secret_ key 权限配置问题")
            print("[INFO] 建议：尝试使用 Legacy service_role key（eyJ... 开头的 JWT）")
        
        print("[WARNING] 将只打印数据，不写入数据库。")
        return None


def init_exchange() -> ccxt.binanceusdm | None:
    """
    初始化币安 USDT 永续合约交易所实例。
    
    注意：如果未配置有效的 API Key，返回 None
    我们将使用公共 API 直接获取数据，避免认证问题
    """
    # 如果没有配置 API Key，返回 None（使用公共 API）
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return None
    
    config: dict = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",  # 使用合约市场
        },
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_API_SECRET,
    }

    exchange = ccxt.binanceusdm(config)
    return exchange


def symbol_to_binance_symbol(symbol: str) -> str:
    """
    将 ccxt 格式的交易对转换为币安合约格式
    例如：TRB/USDT -> TRBUSDT
    """
    return symbol.replace("/", "")


def scan_all_markets_via_public_api() -> dict[str, dict]:
    """
    第一层（粗筛）：使用币安公共 API 一次性获取所有币种的 24h ticker 数据。
    
    返回: {symbol: ticker_data} 字典
    """
    base_url = "https://fapi.binance.com"
    try:
        # 获取所有 USDT 永续合约的 24h ticker
        url = f"{base_url}/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        all_tickers = response.json()
        
        # 转换为 {symbol: data} 字典格式
        result: dict[str, dict] = {}
        for ticker in all_tickers:
            symbol = ticker["symbol"]
            # 只保留 USDT 永续合约
            if symbol.endswith("USDT"):
                result[symbol] = ticker
        
        return result
    except Exception as e:  # noqa: BLE001
        raise Exception(f"全市场扫描失败: {e}")


def detect_movers(tickers: dict[str, dict], supabase: Client | None = None) -> list[tuple[str, float, str]]:
    """
    第一层筛选：找出异动币种。
    
    筛选逻辑：
    1. 剔除 BTC/ETH（只看山寨币）
    2. 剔除 24h 成交量 < 1000万 U 的
    3. 异动检测：
       - 爆拉：5分钟内涨幅 > 2%（需要历史数据）
       - 放量：当前成交量是过去均值的 3 倍（需要历史数据）
       - 新币：昨天不在列表里，今天突然出现的（需要历史数据）
    
    返回: [(symbol, score, reason), ...] 按异动分数降序排列
    """
    movers: list[tuple[str, float, str]] = []
    
    # 排除主流币
    excluded = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}
    
    for symbol, ticker in tickers.items():
        if symbol in excluded:
            continue
        
        # 过滤低成交量
        volume_24h = float(ticker.get("quoteVolume", 0))  # 24h 成交额（USDT）
        if volume_24h < MIN_VOLUME_24H:
            continue
        
        # 计算异动分数（简化版：基于价格变化和成交量）
        price_change_24h = float(ticker.get("priceChangePercent", 0))
        volume_change_24h = float(ticker.get("volume", 0))  # 24h 成交量

        # 可选：过滤极端暴跌（默认关闭，避免误杀“洗盘/插针”场景）
        if SKIP_24H_DROP_PCT is not None and price_change_24h <= SKIP_24H_DROP_PCT:
            continue
        
        # 异动分数 = 价格变化绝对值 + 成交量权重
        score = abs(price_change_24h) + (volume_change_24h / 1_000_000) * 0.1
        
        # 如果 24h 涨幅 > 5% 或跌幅 < -5%，认为是异动
        if abs(price_change_24h) >= 5.0:
            reason = f"24h涨跌{price_change_24h:+.2f}%"
            movers.append((symbol, score, reason))
        # 或者成交量异常大
        elif volume_24h > MIN_VOLUME_24H * 5:
            reason = f"放量{volume_24h/1_000_000:.1f}M"
            movers.append((symbol, score, reason))
    
    # 按分数降序排列，返回 TOP N
    movers.sort(key=lambda x: x[1], reverse=True)
    return movers[:TOP_MOVERS_COUNT]


def binance_symbol_to_ccxt_symbol(binance_symbol: str) -> str:
    """
    将币安格式转换为 ccxt 格式
    例如：TRBUSDT -> TRB/USDT
    """
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}/USDT"
    return binance_symbol


def fetch_long_short_ratio_public(binance_symbol: str) -> float | None:
    """
    获取多空账户比（Long/Short Ratio）
    
    使用币安公共 API：/futures/data/globalLongShortAccountRatio
    不需要认证
    
    注意：某些币种可能不支持此接口，返回 404 是正常的
    """
    try:
        # 正确端点在 /futures/data 下（不是 /fapi/v1）
        url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
        params = {"symbol": binance_symbol, "period": "5m", "limit": 1}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 返回最新的一条数据
        if isinstance(data, list) and len(data) > 0:
            return float(data[0].get("longShortRatio", 1.0))
        elif isinstance(data, dict):
            return float(data.get("longShortRatio", 1.0))
        return None
    except requests.exceptions.HTTPError as e:
        # 404 表示该币种不支持多空比接口，这是正常的
        if e.response and e.response.status_code == 404:
            # 静默处理，不打印警告（某些币种不支持此接口）
            return None
        print(f"[WARNING] 获取多空比失败: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 获取多空比失败: {e}")
        return None


def fetch_price_change_1h_via_klines(binance_symbol: str) -> float | None:
    """
    使用币安公共 K 线接口计算 1H 价格变化率（百分比）。
    这能避免“刚启动数据库没历史行”导致的 price_change=None，从而减少 phase=UNKNOWN。
    """
    try:
        base_url = "https://fapi.binance.com"
        url = f"{base_url}/fapi/v1/klines"
        params = {"symbol": binance_symbol, "interval": "1h", "limit": 2}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return None
        prev_close = float(data[-2][4])
        last_close = float(data[-1][4])
        if prev_close == 0:
            return None
        return (last_close - prev_close) / prev_close * 100.0
    except Exception:
        return None


def fetch_oi_change_1h_via_open_interest_hist(binance_symbol: str) -> float | None:
    """
    使用币安 openInterestHist 接口计算 1H OI 变化率（百分比）。
    某些币种可能返回 400/不支持，返回 None 即可。
    """
    try:
        url = "https://fapi.binance.com/futures/data/openInterestHist"
        params = {"symbol": binance_symbol, "period": "1h", "limit": 2}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return None
        # 可能字段：sumOpenInterest / openInterest（视接口返回而定）
        def _get_oi(x: dict) -> float:
            if "sumOpenInterest" in x and x["sumOpenInterest"] is not None:
                return float(x["sumOpenInterest"])
            if "openInterest" in x and x["openInterest"] is not None:
                return float(x["openInterest"])
            return 0.0

        prev = _get_oi(data[-2])
        last = _get_oi(data[-1])
        if prev == 0:
            return None
        return (last - prev) / prev * 100.0
    except Exception:
        return None


def get_historical_data(supabase: Client | None, symbol: str) -> dict | None:
    """
    从 Supabase 获取 1 小时前的数据，用于计算变化率
    
    返回: {
        "price": float,
        "oi_value": float,
        "timestamp": datetime
    } 或 None（如果没有历史数据）
    """
    if supabase is None:
        return None

    def _query_once(client: Client) -> dict | None:
        # 计算 1 小时前的时间点
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        # 查询 1 小时前最近的一条记录
        response = (
            client.table("ai_training_data")
            .select("price, oi_value, created_at")
            .eq("symbol", symbol)
            .lt("created_at", one_hour_ago.isoformat())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            record = response.data[0]
            return {
                "price": float(record.get("price", 0)),
                "oi_value": float(record.get("oi_value", 0)),
                "timestamp": record.get("created_at"),
            }
        return None

    # Windows 下偶发的 WinError 10035（非阻塞 socket 暂时不可用）通常是底层 HTTP 客户端并发/复用导致的。
    # 这里做两层防御：
    # 1) 先用传入的 supabase client 尝试一次（正常情况下最快）
    # 2) 如遇 10035，短暂退避重试，并在重试时创建“全新 client”避免跨线程复用同一个 http client
    try:
        return _query_once(supabase)
    except OSError as e:
        if getattr(e, "winerror", None) != 10035:
            print(f"[WARNING] 获取历史数据失败: {e}")
            return None
    except Exception as e:  # noqa: BLE001
        # 其它错误保持原行为
        print(f"[WARNING] 获取历史数据失败: {e}")
        return None

    # 仅针对 WinError 10035：退避重试（在 to_thread 里运行，允许 time.sleep）
    try:
        supa_url = os.environ.get("SUPABASE_URL")
        supa_key = os.environ.get("SUPABASE_KEY")
        if not supa_url or not supa_key:
            # 没有环境变量就不重试，避免再次报错刷屏
            return None

        for backoff in (0.05, 0.15, 0.3):
            try:
                time.sleep(backoff)
                fresh = create_client(supa_url, supa_key)
                return _query_once(fresh)
            except OSError as e2:
                if getattr(e2, "winerror", None) == 10035:
                    continue
                print(f"[WARNING] 获取历史数据失败: {e2}")
                return None
            except Exception as e2:  # noqa: BLE001
                print(f"[WARNING] 获取历史数据失败: {e2}")
                return None
    except Exception:
        # 最终兜底：不影响主流程
        return None

    # 多次退避后仍失败：静默返回 None（避免日志刷屏）
    return None


def calculate_changes(current_price: float, current_oi: float, historical: dict | None) -> tuple[float | None, float | None]:
    """
    计算 1 小时变化率
    
    返回: (price_change_pct, oi_change_pct)
    """
    if historical is None:
        return None, None

    prev_price = historical.get("price", 0)
    prev_oi = historical.get("oi_value", 0)

    if prev_price == 0 or prev_oi == 0:
        return None, None

    # 计算百分比变化率
    price_change = ((current_price - prev_price) / prev_price) * 100
    oi_change = ((current_oi - prev_oi) / prev_oi) * 100

    return price_change, oi_change


def fetch_metrics_via_public_api(binance_symbol: str) -> dict:
    """
    使用币安公共 API 直接获取数据（不需要认证）
    避免 ccxt 的认证问题
    """
    base_url = "https://fapi.binance.com"
    
    try:
        # 1. 获取 ticker（24小时价格统计）
        ticker_url = f"{base_url}/fapi/v1/ticker/24hr"
        ticker_params = {"symbol": binance_symbol}
        ticker_response = requests.get(ticker_url, params=ticker_params, timeout=10)
        ticker_response.raise_for_status()
        ticker_data = ticker_response.json()
        last_price = float(ticker_data["lastPrice"])

        # 2. 获取资金费率
        funding_url = f"{base_url}/fapi/v1/premiumIndex"
        funding_params = {"symbol": binance_symbol}
        funding_response = requests.get(funding_url, params=funding_params, timeout=10)
        funding_response.raise_for_status()
        funding_data = funding_response.json()
        funding_rate = float(funding_data.get("lastFundingRate", 0.0))

        # 3. 获取持仓量
        oi_url = f"{base_url}/fapi/v1/openInterest"
        oi_params = {"symbol": binance_symbol}
        oi_response = requests.get(oi_url, params=oi_params, timeout=10)
        oi_response.raise_for_status()
        oi_data = oi_response.json()
        oi_value = float(oi_data["openInterest"])

        return {
            "price": last_price,
            "funding_rate": funding_rate,
            "oi_value": oi_value,
            "raw": {
                "ticker": ticker_data,
                "funding": funding_data,
                "open_interest": oi_data,
            },
        }
    except Exception as e:  # noqa: BLE001
        raise Exception(f"获取币安公共数据失败: {e}")


def fetch_price_and_funding_via_public_api(binance_symbol: str) -> dict:
    """
    轻量：只获取 price + funding（快循环用，接口更快）。
    """
    base_url = "https://fapi.binance.com"

    try:
        # 1) 最新价
        ticker_url = f"{base_url}/fapi/v1/ticker/24hr"
        ticker_params = {"symbol": binance_symbol}
        ticker_response = requests.get(ticker_url, params=ticker_params, timeout=10)
        ticker_response.raise_for_status()
        ticker_data = ticker_response.json()
        last_price = float(ticker_data["lastPrice"])

        # 2) 资金费率（premiumIndex 的 lastFundingRate）
        funding_url = f"{base_url}/fapi/v1/premiumIndex"
        funding_params = {"symbol": binance_symbol}
        funding_response = requests.get(funding_url, params=funding_params, timeout=10)
        funding_response.raise_for_status()
        funding_data = funding_response.json()
        funding_rate = float(funding_data.get("lastFundingRate", 0.0))

        return {
            "price": last_price,
            "funding_rate": funding_rate,
            "raw": {"ticker": ticker_data, "funding": funding_data},
        }
    except Exception as e:  # noqa: BLE001
        raise Exception(f"获取 price/funding 失败: {e}")


def fetch_open_interest_via_public_api(binance_symbol: str) -> float | None:
    """
    慢指标：只获取 OI（openInterest）。
    """
    base_url = "https://fapi.binance.com"
    oi_url = f"{base_url}/fapi/v1/openInterest"
    oi_params = {"symbol": binance_symbol}
    oi_response = requests.get(oi_url, params=oi_params, timeout=10)
    try:
        oi_response.raise_for_status()
    except requests.HTTPError:
        # 某些 symbol 可能已下架/不支持 OI，Binance 会返回 400
        if oi_response.status_code == 400:
            return None
        raise
    oi_data = oi_response.json()
    try:
        return float(oi_data["openInterest"])
    except Exception:  # noqa: BLE001
        return None


def fetch_open_interest_via_ccxt(exchange: ccxt.binanceusdm | None, binance_symbol: str) -> float | None:
    """
    备用：使用 ccxt 调用 openInterest（不同版本方法名可能不同）。
    注意：即使有 API Key，这个接口通常也是公开接口；这里主要用来兼容某些环境下 requests 异常。
    """
    if exchange is None:
        return None
    try:
        # ccxt 常见方法名（随版本变动）：fapiPublicGetOpenInterest
        if hasattr(exchange, "fapiPublicGetOpenInterest"):
            oi_raw = exchange.fapiPublicGetOpenInterest({"symbol": binance_symbol})
            return float(oi_raw.get("openInterest"))
        # 兜底：如果没有该方法，直接返回 None
        return None
    except Exception:  # noqa: BLE001
        return None


def fetch_price_and_funding(symbol: str, exchange: ccxt.binanceusdm | None) -> dict:
    """
    快指标获取：优先公共 API；失败时回退 ccxt（需要配置有效 API Key）。
    """
    binance_symbol = symbol_to_binance_symbol(symbol)

    try:
        return fetch_price_and_funding_via_public_api(binance_symbol)
    except Exception as e:  # noqa: BLE001
        if exchange is None:
            raise Exception(f"无法获取 {symbol} price/funding：公共 API 失败且未配置交易所实例：{e}")
        ticker = exchange.fetch_ticker(symbol)
        funding = exchange.fetch_funding_rate(symbol)
        return {
            "price": float(ticker["last"]),
            "funding_rate": float(funding.get("fundingRate", 0.0)),
            "raw": {},
        }


def fetch_slow_metrics(symbol: str, exchange: ccxt.binanceusdm | None) -> dict:
    """
    慢指标获取：OI + LS Ratio（每 60 秒跑一次）。
    """
    binance_symbol = symbol_to_binance_symbol(symbol)

    # OI：优先公共 API；如果返回 None（400/不可用），尝试 ccxt 备用；都失败则置空，不抛异常（避免整条深度采集失败）
    oi_value: float | None = None
    try:
        oi_value = fetch_open_interest_via_public_api(binance_symbol)
    except Exception as e:  # noqa: BLE001
        # 非 400 错误（例如网络），尝试 ccxt 备用
        oi_value = fetch_open_interest_via_ccxt(exchange, binance_symbol)
        if oi_value is None:
            print(f"[WARNING] OI 获取失败（将跳过 OI）{symbol}: {e}")

    if oi_value is None:
        # 400 或无法获取：再试一次 ccxt 备用（可能某些环境下 requests 失败但 ccxt 可用）
        oi_value = fetch_open_interest_via_ccxt(exchange, binance_symbol)

    # LS：公共 API（部分币种可能不支持，返回 None）
    ls_ratio = fetch_long_short_ratio_public(binance_symbol)

    return {"oi_value": oi_value, "ls_ratio": ls_ratio}


def safe_enqueue(queue: asyncio.Queue, item: dict, symbol: str = "", table: str = "") -> None:
    """
    安全入队：队满时打印 [CRITICAL] 日志而不是静默丢弃。
    """
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        print(f"[CRITICAL] 写入队列已满，丢弃数据 symbol={symbol} table={table}（当前队列大小: {queue.qsize()}）")


async def _supabase_write_worker(queue: asyncio.Queue, supabase: Client) -> None:
    """
    后台写库 worker：串行消费写入任务，避免阻塞采集循环。
    任务格式：{"op": "insert"|"upsert", "table": str, "row": dict, "on_conflict": Optional[str]}
    """
    while True:
        try:
            item = await queue.get()
            op = item.get("op")
            table = item.get("table")
            row = item.get("row")
            on_conflict = item.get("on_conflict")

            if op == "insert":
                try:
                    await asyncio.to_thread(lambda: supabase.table(table).insert(row).execute())
                except Exception as e:  # noqa: BLE001
                    # 详细错误信息
                    error_msg = str(e)
                    if "Could not find the table" in error_msg or "relation" in error_msg.lower():
                        print(f"[ERROR] 表 '{table}' 不存在，请检查数据库迁移是否完成")
                    elif "column" in error_msg.lower() and "does not exist" in error_msg.lower():
                        print(f"[ERROR] 表 '{table}' 缺少必需的列，请检查数据库 schema")
                    else:
                        print(f"[WARNING] Supabase 写入失败 ({table}): {error_msg[:200]}")
                    # 打印完整 traceback（仅在调试模式）
                    if os.environ.get("SUPABASE_DEBUG", "0") in ("1", "true", "True"):
                        import traceback
                        traceback.print_exc()
            elif op == "upsert":
                try:
                    await asyncio.to_thread(lambda: supabase.table(table).upsert(row, on_conflict=on_conflict).execute())
                except Exception as e:  # noqa: BLE001
                    error_msg = str(e)
                    if "Could not find the table" in error_msg or "relation" in error_msg.lower():
                        print(f"[ERROR] 表 '{table}' 不存在，请检查数据库迁移是否完成")
                    else:
                        print(f"[WARNING] Supabase 更新失败 ({table}): {error_msg[:200]}")
                    if os.environ.get("SUPABASE_DEBUG", "0") in ("1", "true", "True"):
                        import traceback
                        traceback.print_exc()
            else:
                print(f"[WARNING] 未知写入任务类型: {op}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] 写库 worker 异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # 不要退出 worker，继续处理下一个任务
        finally:
            try:
                queue.task_done()
            except Exception:
                pass


def _build_snapshot_row(symbol: str, now_iso: str, metrics: dict) -> dict:
    price = float(metrics["price"])
    funding_rate = float(metrics["funding_rate"])

    market_phase = metrics.get("market_phase")
    kill_zone_signal = metrics.get("kill_zone_signal")
    exit_clarity_score = metrics.get("exit_clarity_score")
    confidence_level = metrics.get("confidence_level")
    ai_score = metrics.get("ai_score")
    ai_allowed = metrics.get("ai_allowed")
    ai_reason = metrics.get("ai_reason")
    ai_version = metrics.get("ai_version")
    p3a_match_score = metrics.get("p3a_match_score")
    ai_effective_threshold = metrics.get("ai_effective_threshold")
    ls_ratio = metrics.get("ls_ratio")

    market_regime, risk_reasons, risk_score = compute_v4_snapshot(
        market_phase=market_phase,
        kill_zone_signal=kill_zone_signal,
        exit_clarity_score=exit_clarity_score,
        funding_rate=funding_rate,
        confidence_level=confidence_level,
        ls_ratio=ls_ratio,
    )

    return {
        "symbol": symbol,
        "price": price,
        "funding_rate": funding_rate,
        "risk_score": risk_score,
        "risk_level": ("DANGER" if risk_score >= 80 else "WARNING" if risk_score >= 50 else "SAFE"),
        "regime": market_regime,
        "updated_at": now_iso,
        # AI 展示字段（用于前端雷达）
        "ai_score": ai_score,
        "ai_allowed": ai_allowed,
        "ai_reason": ai_reason,
        "ai_version": ai_version,
        "p3a_match_score": p3a_match_score,
        "ai_effective_threshold": ai_effective_threshold,
    }


def fetch_klines_for_indicators(binance_symbol: str, limit: int = 100) -> list[float]:
    """
    获取K线数据用于计算技术指标
    
    Args:
        binance_symbol: 币安格式的交易对，如 "TRBUSDT"
        limit: 获取的K线数量，默认 100（需要至少 50 个数据点）
    
    Returns:
        价格列表（从旧到新），每个元素是收盘价
    """
    base_url = "https://fapi.binance.com"
    
    try:
        # 获取 1小时K线数据
        klines_url = f"{base_url}/fapi/v1/klines"
        params = {
            "symbol": binance_symbol,
            "interval": "1h",  # 1小时K线
            "limit": limit
        }
        response = requests.get(klines_url, params=params, timeout=10)
        response.raise_for_status()
        klines = response.json()
        
        # 提取收盘价（索引 4）
        prices = [float(k[4]) for k in klines]
        return prices
        
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 获取 {binance_symbol} K线数据失败: {e}")
        return []


def fetch_klines_full(binance_symbol: str, interval: str = "15m", limit: int = 100) -> tuple[list[float], list[float], list[float]]:
    """
    获取完整 K 线数据（highs, lows, closes）用于 V4.1 计算
    
    Args:
        binance_symbol: 币安格式的交易对，如 "TRBUSDT"
        interval: K 线间隔，如 "15m", "1h", "4h"
        limit: 获取的K线数量，默认 100
    
    Returns:
        (highs, lows, closes) 三个列表，每个元素是价格（从旧到新）
    """
    base_url = "https://fapi.binance.com"
    
    try:
        klines_url = f"{base_url}/fapi/v1/klines"
        params = {
            "symbol": binance_symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(klines_url, params=params, timeout=10)
        response.raise_for_status()
        klines = response.json()
        
        # K 线格式：[开盘时间, 开盘价, 最高价, 最低价, 收盘价, ...]
        # 索引：0=开盘时间, 1=开盘价, 2=最高价, 3=最低价, 4=收盘价
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        
        return highs, lows, closes
        
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 获取 {binance_symbol} {interval} K线数据失败: {e}")
        return [], [], []


def fetch_klines_ohlcv(binance_symbol: str, interval: str = "1h", limit: int = 100) -> list[dict]:
    """
    获取完整 OHLCV K 线数据（用于 Level 1 结构层分析）
    
    Args:
        binance_symbol: 币安格式的交易对，如 "TRBUSDT"
        interval: K 线间隔，如 "1h", "4h"
        limit: 获取的K线数量，默认 100
    
    Returns:
        [{"open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
        从旧到新排列
    """
    base_url = "https://fapi.binance.com"
    
    try:
        klines_url = f"{base_url}/fapi/v1/klines"
        params = {
            "symbol": binance_symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(klines_url, params=params, timeout=10)
        response.raise_for_status()
        klines = response.json()
        
        # K 线格式：[开盘时间, 开盘价, 最高价, 最低价, 收盘价, 成交量, ...]
        # 索引：0=开盘时间, 1=开盘价, 2=最高价, 3=最低价, 4=收盘价, 5=成交量
        result = []
        for k in klines:
            result.append({
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        
        return result
        
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 获取 {binance_symbol} {interval} OHLCV 数据失败: {e}")
        return []


def _build_ai_training_row(
    symbol: str, 
    now_iso: str, 
    metrics: dict, 
    supabase: Client | None = None,
    exchange: ccxt.binanceusdm | None = None
) -> dict:
    """
    构建写入 ai_training_data 的行数据（慢循环每 60 秒写一次）。
    
    现在包含策略信号生成逻辑。
    """
    price = float(metrics["price"])
    funding_rate = float(metrics["funding_rate"])
    oi_value = metrics.get("oi_value")
    ls_ratio = metrics.get("ls_ratio")
    price_change = metrics.get("price_change")
    oi_change = metrics.get("oi_change")
    cvd_data = metrics.get("cvd_data")
    oi_series = metrics.get("oi_series")

    # 判断是否发生 OI 背离
    is_oi_divergence = False
    if price_change is not None and oi_change is not None:
        if (price_change > 0 and oi_change < -5) or (price_change < 0 and oi_change < -5):
            is_oi_divergence = True

    # V2 逻辑已移除：不再使用 Whale Matrix 的风控优先判定。
    # 旧字段名仍保留给前端兼容，但决策以 V4（phase/kill_zone/exit_clarity/confidence）为主。
    market_regime = "UNKNOWN"
    risk_reasons: list[str] = []
    is_trade_allowed = False
    risk_score = 0

    # ========== Rabbit Hunter 4.0：使用（可选）CVD + 价格/OI/资金费率推断 Phase（P 阶段）+ Kill Zone ==========
    market_phase: str | None = None
    cvd_value: float | None = None
    cvd_15m: float | None = None
    cvd_1h: float | None = None
    kill_zone_signal: str | None = None
    exit_clarity_score: int | None = None
    v4_trade_allowed: bool = False

    try:
        # 旧逻辑要求 cvd_data 才推断，导致短数据期 / CVD 缺失时 market_phase/kill_zone 全为空
        # 这里改为：只要有 price_change，就用“CVD=NEUTRAL”的兜底推断出至少 UNKNOWN/NONE，确保回测/分层可用
        if price_change is not None:
            from cvd_analyzer import CVDAnalyzer  # 局部导入，避免循环依赖
            from whale_detector import (
                check_kill_zones,
                compute_exit_clarity_score,
                detect_phase,
                is_oi_second_spike_confirmed,
                PHASE_P2,
                PHASE_P3A,
            )

            cvd_intent = "NEUTRAL"
            analyzer = CVDAnalyzer(None)
            if cvd_data:
                cvd_15m = float(cvd_data.get("cvd_15m", cvd_data.get("cvd_volume", 0.0)) or 0.0)
                cvd_1h = float(cvd_data.get("cvd_1h", 0.0) or 0.0)
                # v4：默认用 15m 作为“当前 CVD”
                cvd_value = cvd_15m
                try:
                    cvd_intent = analyzer.analyze_cvd_intent(float(price_change) / 100.0, cvd_data)  # price_change 为百分比
                except Exception:
                    cvd_intent = "NEUTRAL"

            # Phase：P1-P4
            market_phase = detect_phase(
                price_change_1h=price_change,
                oi_change_1h=oi_change,
                cvd_intent=cvd_intent,
                cvd_1h=cvd_1h,
                whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
            )

            # 强制验证：P3a 必须伴随 OI 二次放量（不满足则降级为 P2）
            oi_second_spike_ok = is_oi_second_spike_confirmed(oi_series)
            if market_phase == PHASE_P3A and not oi_second_spike_ok:
                market_phase = PHASE_P2

            # Kill Zones：三大猎杀场景
            price_breakout = True if price_change is not None and price_change > 2.0 else False
            # 工程化近似：用 1h 跌幅近似“闪崩”，OI 不显著下降近似“稳定”
            flash_crash = True if (price_change is not None and price_change < -2.0) else False
            oi_stable = True if (oi_change is None or oi_change > -1.0) else False
            kill_zone_signal = check_kill_zones(
                funding_rate=funding_rate,
                oi_change_1h=oi_change,
                price_breakout=price_breakout,
                cvd_intent=cvd_intent,
                phase=market_phase,
                flash_crash=flash_crash,
                oi_stable=oi_stable,
            )

            # 退出条件清晰度评分（0-100）
            exit_clarity_score = compute_exit_clarity_score(
                phase=market_phase,
                kill_zone=kill_zone_signal or "NONE",
                funding_rate=funding_rate,
                oi_change_1h=oi_change,
                price_change_1h=price_change,
                cvd_intent=cvd_intent,
                oi_second_spike_confirmed=oi_second_spike_ok,
            )

            # V4 是否允许“跟庄”：用 phase/kill_zone/exit_clarity 做主判定（risk_score 只做展示）
            # P3a：允许跟庄；P2：只允许吸筹小仓；P3b/P4：禁止追；P1：禁止
            if market_phase == "P3A_PUMP_START" and (exit_clarity_score or 0) >= 70:
                v4_trade_allowed = True
            elif market_phase == "P2_ACCUMULATION" and (kill_zone_signal == "ACCUMULATION") and (exit_clarity_score or 0) >= 55:
                v4_trade_allowed = True
            else:
                v4_trade_allowed = False
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 推断市场阶段/ Kill Zone 失败: {e}")
        market_phase = market_phase or "UNKNOWN"
        kill_zone_signal = kill_zone_signal or "NONE"

    # 兜底：确保内存中的阶段/猎杀区字段稳定（用于后续 V4/V4.1 逻辑与前端展示）
    # 注意：ai_training_data 表中的 market_phase 是 phase_type 枚举，只接受 P1~P4，不能写入 "UNKNOWN"
    market_phase = market_phase or "UNKNOWN"
    kill_zone_signal = kill_zone_signal or "NONE"

    # ========== V4.1 计算（ATR、结构空间、多周期 Context、Phase Age）==========
    atr_value: float | None = None
    atr_multiplier: float | None = None
    structure_gap: float | None = None
    structure_gap_method: str | None = None
    phase_age_candles: int | None = None
    phase_age_percent: float | None = None
    v41_block_reason: str | None = None
    chandelier_stop_price: float | None = None
    position_size_coin: float | None = None
    phase_4h: str | None = None
    phase_1h: str | None = None
    
    try:
        binance_symbol = symbol_to_binance_symbol(symbol)
        
        # 1. 获取 15m K 线数据（用于 ATR 计算）
        highs_15m, lows_15m, closes_15m = fetch_klines_full(binance_symbol, interval="15m", limit=100)
        if len(highs_15m) >= 15 and len(lows_15m) >= 15 and len(closes_15m) >= 15:
            try:
                from v41_risk_manager import calculate_atr, get_atr_multiplier, calculate_chandelier_stop, calculate_position_size
                from v41_structure_analyzer import calculate_structure_gap
                from v41_context_gate import get_phase_for_timeframe, calculate_phase_age, check_phase_age_block
                
                # 计算 ATR（不依赖 market_phase，只要有 K 线数据就计算）
                atr_value = calculate_atr(highs_15m, lows_15m, closes_15m, length=14)
                
                # 获取 ATR 倍数（需要 market_phase）
                # 注意：即使 market_phase 为 null，也应该计算 ATR（因为 ATR 是基础指标）
                if atr_value and atr_value > 0:
                    # 只有当 market_phase 存在时，才计算 atr_multiplier 和 chandelier_stop_price
                    if market_phase and market_phase != "UNKNOWN":
                        atr_multiplier = get_atr_multiplier(market_phase, phase_age_percent)
                        
                        # 计算吊灯止损（假设做多）
                        if atr_multiplier:
                            chandelier_stop_price = calculate_chandelier_stop(
                                entry_price=price,
                                atr_value=atr_value,
                                atr_multiplier=atr_multiplier,
                                highest_high_since_entry=None,  # 初始止损，没有历史最高价
                                is_long=True
                            )
                            
                            # 计算动态仓位（假设账户余额 10000 USDT，单笔风险 1.5%）
                            account_balance = 10000.0  # TODO: 从配置读取
                            position_size_coin = calculate_position_size(
                                account_balance=account_balance,
                                entry_price=price,
                                stop_loss_price=chandelier_stop_price,
                                risk_per_trade=0.015
                            )
            except ImportError:
                pass  # V4.1 模块未安装，跳过
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] {symbol} V4.1 ATR 计算失败: {e}")
        
        # 2. 获取 1H K 线数据（用于结构空间计算和多周期 Context）
        highs_1h, lows_1h, closes_1h = fetch_klines_full(binance_symbol, interval="1h", limit=100)
        if len(highs_1h) >= 20 and len(closes_1h) >= 20:
            try:
                from v41_structure_analyzer import calculate_structure_gap
                from v41_context_gate import get_phase_for_timeframe
                
                # 计算结构空间
                structure_gap, structure_gap_method = calculate_structure_gap(
                    current_price=price,
                    highs_1h=highs_1h,
                    closes_1h=closes_1h,
                    use_bollinger=True
                )
                
                # 计算 1H 周期的 P 阶段（用于 Context Gate）
                if price_change is not None and oi_change is not None:
                    cvd_intent_local = cvd_intent if 'cvd_intent' in locals() else "NEUTRAL"
                    phase_1h = get_phase_for_timeframe(
                        price_change_1h=price_change,
                        oi_change_1h=oi_change,
                        cvd_intent=cvd_intent_local,
                        cvd_1h=cvd_1h,
                        whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
                    )
            except ImportError:
                pass
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] {symbol} V4.1 结构空间计算失败: {e}")
        
        # 3. 获取 4H K 线数据（用于多周期 Context）
        # 注意：4H 需要计算价格变化和 OI 变化，这里简化处理
        try:
            from v41_context_gate import get_phase_for_timeframe
            # TODO: 获取 4H 周期的 price_change 和 oi_change
            # 暂时使用 1H 数据近似
            if price_change is not None and oi_change is not None:
                cvd_intent_local = cvd_intent if 'cvd_intent' in locals() else "NEUTRAL"
                phase_4h = get_phase_for_timeframe(
                    price_change_1h=price_change * 0.5,  # 4H 变化通常更小
                    oi_change_1h=oi_change * 0.5,
                    cvd_intent=cvd_intent_local,
                    cvd_1h=cvd_1h,
                    whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
                )
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[WARNING] {symbol} V4.1 4H 阶段计算失败: {e}")
        
        # 4. 计算 Phase Age（需要从数据库查询阶段开始时间）
        # 改进：即使当前 market_phase 为 null，也尝试从历史记录中查找最近的 phase 来计算
        if supabase is not None:
            try:
                from v41_context_gate import calculate_phase_age
                
                # 确定要使用的 phase（优先使用当前 phase，如果为 null 则从历史记录查找）
                phase_to_use = market_phase if market_phase and market_phase != "UNKNOWN" else None
                
                # 查询该币种最近一条有 phase 的记录
                recent_response = (
                    supabase.table("ai_training_data")
                    .select("market_phase, created_at")
                    .eq("symbol", symbol)
                    .not_.is_("market_phase", "null")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                
                phase_start_time: datetime | None = None
                current_time = datetime.now(timezone.utc)
                
                if recent_response.data and len(recent_response.data) > 0:
                    last_record = recent_response.data[0]
                    last_phase = last_record.get("market_phase")
                    last_created_at_str = last_record.get("created_at")
                    
                    # 如果当前 phase 为 null，使用历史记录的 phase
                    if not phase_to_use:
                        phase_to_use = last_phase
                    
                    # 如果阶段相同（或使用历史 phase），需要找到该阶段第一次出现的时间
                    if phase_to_use and last_phase == phase_to_use:
                        # 查询该阶段第一次出现的时间（阶段开始时间）
                        phase_start_response = (
                            supabase.table("ai_training_data")
                            .select("created_at")
                            .eq("symbol", symbol)
                            .eq("market_phase", phase_to_use)
                            .order("created_at", desc=False)  # 从旧到新
                            .limit(1)
                            .execute()
                        )
                        
                        if phase_start_response.data and len(phase_start_response.data) > 0:
                            phase_start_str = phase_start_response.data[0].get("created_at")
                            if phase_start_str:
                                try:
                                    # 解析 ISO 格式时间字符串
                                    if isinstance(phase_start_str, str):
                                        # 处理带时区的 ISO 格式
                                        if phase_start_str.endswith("Z"):
                                            phase_start_str = phase_start_str[:-1] + "+00:00"
                                        phase_start_time = datetime.fromisoformat(phase_start_str.replace("Z", "+00:00"))
                                    else:
                                        phase_start_time = None
                                except Exception:
                                    phase_start_time = None
                    elif phase_to_use and last_phase != phase_to_use:
                        # 阶段不同，说明阶段刚变化，开始时间就是当前时间
                        phase_start_time = current_time
                
                # 如果找不到历史记录，但 phase_to_use 存在，则从当前时间开始计算
                if phase_start_time is None and phase_to_use:
                    phase_start_time = current_time
                
                # 计算 Phase Age
                if phase_start_time:
                    phase_age_candles, phase_age_percent = calculate_phase_age(
                        phase_start_time=phase_start_time,
                        current_time=current_time,
                        candle_interval_minutes=15
                    )
            except ImportError:
                pass  # v41_context_gate 未导入，跳过
            except Exception as e:  # noqa: BLE001
                # Phase Age 计算失败不影响主流程，静默处理
                pass
        
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] {symbol} V4.1 计算失败: {e}")
    
    # ========== V4.2 Golden Wick (定海神针) 检测 + 墓碑线检测 ==========
    is_golden_wick: bool = False
    golden_wick_details: dict | None = None
    ohlcv_15m: list[dict] | None = None
    oi_change_15m: float | None = None
    tombstone_confirmed: bool = False
    
    try:
        binance_symbol = symbol_to_binance_symbol(symbol)
        
        # 获取 15m OHLCV 数据（用于 Golden Wick 检测）
        ohlcv_15m = fetch_klines_ohlcv(binance_symbol, interval="15m", limit=20)
        
        # 改进：即使数据不足，也尝试检测（降低要求）
        if len(ohlcv_15m) >= 10:  # 降低要求：至少 10 根 K 线（2.5 小时）
            try:
                from golden_wick_detector import detect_golden_wick
                
                # 如果数据不足 20 根，调整 lookback_period
                lookback = min(20, len(ohlcv_15m))
                
                is_golden_wick, golden_wick_details = detect_golden_wick(
                    ohlcv_15m=ohlcv_15m,
                    min_wick_ratio=0.6,
                    lookback_period=lookback,
                    sweep_window=2
                )
                
                if is_golden_wick:
                    print(f"[INFO] {symbol} 检测到定海神针 (Golden Wick): {golden_wick_details.get('reason', '')}")
            except ImportError:
                pass  # golden_wick_detector 未安装，跳过
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] {symbol} Golden Wick 检测失败: {e}")
        # 注意：如果数据不足，is_golden_wick 保持为 False（默认值），这是正确的
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] {symbol} Golden Wick 检测异常: {e}")
        # 异常时，is_golden_wick 保持为 False（默认值）
    
    # ========== V4.2 策略信号生成（已废弃，V4.3 使用新的打分系统）==========
    # 注意：V4.3 不再使用 generate_trade_signal，而是使用 V4.3 打分系统
    # 保留此部分仅用于兼容性，technical_signal 将保持为 None
    technical_signal = None
    strategy_confidence_level: int | None = None
    
    # V4.3 使用新的打分系统，不再调用旧的 strategy_engine
    # 如果需要技术信号，可以从 V4.3 的 decision_result 中获取
    # 旧代码已注释，避免导入已废弃的 strategy_engine
    """
    try:
        # 获取K线数据用于计算技术指标
        binance_symbol = symbol_to_binance_symbol(symbol)
        prices = fetch_klines_for_indicators(binance_symbol, limit=100)
        
        if len(prices) >= 20:  # 至少需要 20 个数据点
            # V4.2 策略引擎已废弃，不再调用
            # V4.3 使用新的打分系统（在 V4.3 集成部分处理）
            pass
    except Exception as e:
        print(f"[WARNING] {symbol} 策略信号生成失败: {e}")
    """

    # ========== Rabbit Hunter 4.0：Anti-Confidence Engine（反身性压制） ==========
    confidence_level: int | None = None
    try:
        if strategy_confidence_level is not None:
            from execution_guard import AntiConfidenceEngine

            engine = AntiConfidenceEngine(supabase)
            confidence_level = engine.compute_confidence_level(strategy_confidence_level)
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] Anti-Confidence 计算失败: {e}")

    # V4 最终放行：反身性压制优先（confidence_level 太高则踩刹车）
    final_trade_allowed = bool(is_trade_allowed or v4_trade_allowed)
    if confidence_level is not None and confidence_level >= 80:
        final_trade_allowed = False
        if risk_reasons is not None:
            risk_reasons.append("ANTI_CONFIDENCE_BRAKE")

    # 用 V4 信号生成展示用的 market_regime/risk_reasons/risk_score（同时给前端 snapshot/详情页用）
    try:
        market_regime, v4_reasons, risk_score = compute_v4_snapshot(
            market_phase=market_phase,
            kill_zone_signal=kill_zone_signal,
            exit_clarity_score=exit_clarity_score,
            funding_rate=funding_rate,
            confidence_level=confidence_level,
            ls_ratio=ls_ratio,
        )
        risk_reasons.extend(v4_reasons)
    except Exception:
        pass

    # ========== 将内部阶段字符串安全映射到数据库枚举 ==========
    # phase_type 仅支持：P1_NO_WHALE / P2_ACCUMULATION / P3A_PUMP_START / P3B_PUMP_LATE / P4_DISTRIBUTION
    # 对于推断失败或暂时无法判定的情况，数据库字段应为 NULL，而不是写入 "UNKNOWN"
    valid_phase_values = {
        "P1_NO_WHALE",
        "P2_ACCUMULATION",
        "P3A_PUMP_START",
        "P3B_PUMP_LATE",
        "P4_DISTRIBUTION",
    }
    db_market_phase = market_phase if market_phase in valid_phase_values else None

    return {
        "created_at": now_iso,
        "symbol": symbol,
        "price": price,
        "funding_rate": funding_rate,
        "long_short_ratio": ls_ratio,
        "oi_value": float(oi_value) if oi_value is not None else None,
        "oi_change_1h": oi_change,
        "price_change_1h": price_change,
        "is_oi_divergence": is_oi_divergence if price_change is not None and oi_change is not None else None,
        "market_regime": market_regime,
        "risk_reasons": risk_reasons or None,
        "is_trade_allowed": final_trade_allowed,
        "technical_signal": technical_signal,
        # V4.0 新增字段
        "cvd_15m": cvd_15m,
        "cvd_1h": cvd_1h,
        "cvd_value": cvd_value,
        # 数据库存枚举字段：仅写入合法 P 阶段，其他情况写 NULL，避免 phase_type 枚举报错
        "market_phase": db_market_phase,
        "kill_zone_signal": kill_zone_signal,
        "exit_clarity_score": exit_clarity_score,
        "confidence_level": confidence_level,
        "price_breakout": True if price_change is not None and price_change > 2.0 else False,
        "time_stop_loss_triggered": None,
        "profit_1h": None,
        # V4.1 新增字段
        "atr_value": atr_value,
        "atr_multiplier": atr_multiplier,
        "structure_gap": structure_gap,
        "structure_gap_method": structure_gap_method,
        "phase_age_candles": phase_age_candles,
        "phase_age_percent": phase_age_percent,
        "v41_block_reason": v41_block_reason,
        "chandelier_stop_price": chandelier_stop_price,
        "position_size_coin": position_size_coin,
        "phase_4h": phase_4h,
        "phase_1h": phase_1h,
        # V4.2 新增字段
        "is_golden_wick": is_golden_wick,
    }

"""
V2 旧实现（单币种采集 + Whale Matrix 风控优先写库）已移除。
当前仅保留 V4 三层漏斗主循环（main_loop）作为唯一入口。
"""


def _normalize_binance_symbol(s: str) -> str:
    """将 ccxt 格式/币安格式统一为币安格式：TRB/USDT -> TRBUSDT"""
    return s.replace("/", "").upper()


def should_store_to_ai_training(symbol: str, top_movers: list[tuple[str, float, str]], metrics: dict) -> tuple[bool, str]:
    """
    第三层（存储策略 - Shadow Mode 宽进严出）：判断是否应该写入 ai_training_data。
    
    V4.2 影子模式：使用宽松标准采集数据，但严格标准控制交易。
    
    返回: (should_store, training_tag)
    - should_store: 是否应该存储
    - training_tag: 数据标签 ('PERFECT', 'POTENTIAL', 'SHADOW')
    
    宽松采集标准（Shadow Mode）：
    1. Top N 异动币种（无论是否完美）
    2. 费率 < -0.001% (只要负费率就记录，不要求-0.02%)
    3. 价格变化 > 1% (只要涨了就关注)
    4. 有针形态 (Wick > 40%)
    5. 任何 P2+ 阶段（不要求完美）
    6. 任何 Kill Zone 信号（不要求完美）
    
    严格交易标准（在 is_trade_allowed 中体现）：
    - 只有 PERFECT 标签的数据才允许实盘交易
    """
    sym_binance = _normalize_binance_symbol(symbol)
    
    # 检查是否在 Top N 异动列表中（宽松：只要在列表就存）
    top_symbols = [_normalize_binance_symbol(m[0]) for m in top_movers[:STORE_TOP_COUNT]]
    is_top_mover = sym_binance in top_symbols
    
    # 宽松采集标准（Shadow Mode）
    funding_rate = metrics.get("funding_rate")
    price_change_1h = metrics.get("price_change_1h")
    price_change_24h = metrics.get("price_change_24h")  # 如果有24h数据
    kz = (metrics.get("kill_zone_signal") or "NONE").upper()
    phase = (metrics.get("market_phase") or "P1_NO_WHALE").upper()
    exit_score = metrics.get("exit_clarity_score")
    is_golden_wick = metrics.get("is_golden_wick", False)
    
    # 计算针形态（如果有OHLCV数据）
    wick_ratio = 0.0
    try:
        # 尝试从metrics中获取wick信息，如果没有则从ohlcv计算
        ohlcv_15m = metrics.get("ohlcv_15m")
        if ohlcv_15m and len(ohlcv_15m) > 0:
            latest = ohlcv_15m[-1]
            high = float(latest.get("high", 0))
            low = float(latest.get("low", 0))
            open_price = float(latest.get("open", 0))
            close_price = float(latest.get("close", 0))
            if high > low > 0:
                upper_wick = high - max(open_price, close_price)
                lower_wick = min(open_price, close_price) - low
                candle_range = high - low
                wick_ratio = max(upper_wick, lower_wick) / candle_range if candle_range > 0 else 0.0
    except Exception:
        pass
    
    # 宽松条件检查（只要满足任一条件就存）
    loose_conditions = []
    
    if is_top_mover:
        loose_conditions.append("TOP_MOVER")
    
    # 费率条件：只要负费率就记录（从-0.02%放宽到-0.001%）
    if funding_rate is not None and funding_rate < -0.00001:  # -0.001%
        loose_conditions.append("NEG_FUNDING")
    
    # 价格变化：只要涨了1%就关注（不要求2%）
    if price_change_1h is not None and price_change_1h > 1.0:
        loose_conditions.append("PRICE_UP_1H")
    if price_change_24h is not None and abs(price_change_24h) > 5.0:
        loose_conditions.append("PRICE_MOVE_24H")
    
    # 针形态：只要Wick > 40%就记录（不要求60%）
    if wick_ratio > 0.4:
        loose_conditions.append("WICK_PATTERN")
    
    # 阶段条件：任何P2+阶段都存（不要求完美）
    if phase not in ("P1_NO_WHALE", "UNKNOWN", None):
        loose_conditions.append(f"PHASE_{phase}")
    
    # Kill Zone：任何信号都存（不要求完美）
    if kz != "NONE":
        loose_conditions.append(f"KZ_{kz}")
    
    # Golden Wick：定海神针直接存
    if is_golden_wick:
        loose_conditions.append("GOLDEN_WICK")
    
    # 退出清晰度：降低门槛（从60降到40）
    if isinstance(exit_score, int) and exit_score >= 40:
        loose_conditions.append("EXIT_CLARITY")
    
    # 如果没有任何宽松条件，不存储
    if not loose_conditions:
        return False, "NONE"
    
    # 判断数据质量等级
    is_trade_allowed = metrics.get("is_trade_allowed", False)
    structure_gap = metrics.get("structure_gap")
    
    # PERFECT: 允许交易 + 结构空间 > 2% + 完美条件
    if is_trade_allowed and structure_gap is not None and structure_gap > 0.02:
        # 进一步检查是否真的是完美条件
        if funding_rate is not None and funding_rate < -0.0002:  # -0.02%
            if phase in ("P2_ACCUMULATION", "P3A_PUMP_START"):
                return True, "PERFECT"
    
    # POTENTIAL: 接近完美但不够严格
    if phase in ("P2_ACCUMULATION", "P3A_PUMP_START", "P3B_PUMP_LATE"):
        if funding_rate is not None and funding_rate < -0.0001:  # -0.01%
            return True, "POTENTIAL"
    
    # SHADOW: 其他所有宽松条件的数据（用于AI学习负样本）
    return True, "SHADOW"


async def main_loop() -> None:
    """
    三层漏斗筛选系统主循环：
    
    第一层（粗筛）：每 1 秒扫描全市场，找出异动 TOP 10
    第二层（精筛）：每 60 秒对 TOP 10 做深度采集（OI、费率、LS Ratio）
    第三层（存储）：只存 Top 5 异动币种 + Whale Alert 触发币种
    """
    exchange = init_exchange()
    supabase = init_supabase()

    # 为 CVD 分析单独初始化一个公开行情用的交易所实例（不依赖 API Key）
    cvd_exchange_config: dict = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    }
    cvd_exchange = ccxt.binanceusdm(cvd_exchange_config)
    cvd_analyzer = CVDAnalyzer(cvd_exchange)

    ai_judge = None
    if AI_JUDGE_ENABLED and AIJudge is not None:
        try:
            ai_judge = AIJudge(allowed_threshold=AI_JUDGE_THRESHOLD)
            # 不强制要求模型文件存在：不存在则 predict 返回 None
        except Exception:
            ai_judge = None

    deepseek_judge = None
    if DEEPSEEK_ENABLED and DeepSeekJudge is not None:
        try:
            # V4.2 升级：启用学习功能，传入 supabase 客户端
            deepseek_judge = DeepSeekJudge(
                model=DEEPSEEK_MODEL,
                enable_learning=True,  # 启用学习功能
                supabase=supabase,     # 传入 supabase 用于查询历史数据
            )
            if not deepseek_judge.is_ready():
                deepseek_judge = None
            elif deepseek_judge.learner is not None:
                print("[INFO] ✅ DeepSeek AI 学习功能已启用（V4.2）")
        except Exception:
            deepseek_judge = None

    # 打印 AI 配置状态（不输出任何密钥）
    try:
        local_model_path = os.environ.get("AI_JUDGE_MODEL_PATH") or "models/ai_judge_lr_v1.npz"
        local_model_exists = Path(local_model_path).exists()
        print(
            "[INFO] AI 裁决配置："
            f" DeepSeek={'ON' if DEEPSEEK_ENABLED else 'OFF'}"
            f" model={DEEPSEEK_MODEL}"
            f" key={'SET' if bool(os.environ.get('DEEPSEEK_API_KEY')) else 'MISSING'}"
            f" cache={DEEPSEEK_CACHE_SECONDS}s"
            f" | LocalLR={'ON' if AI_JUDGE_ENABLED else 'OFF'}"
            f" model_file={'FOUND' if local_model_exists else 'MISSING'}"
            f" thr={AI_JUDGE_THRESHOLD:.2f}"
        )
    except Exception:
        pass

    # DeepSeek 缓存：避免同一 symbol 频繁调用（按 seconds 节流）
    deepseek_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # P3a 模式匹配器（启动时构建 profile）
    p3a_matcher = None
    if P3A_MATCH_ENABLED and supabase is not None:
        try:
            from p3a_pattern_matcher import P3APatternMatcher, PatternConfig

            p3a_matcher = P3APatternMatcher(
                supabase,
                PatternConfig(days=P3A_MATCH_DAYS, min_success_samples=P3A_MATCH_MIN_SAMPLES),
            )
            prof = p3a_matcher.fit()
            if prof is not None and p3a_matcher.is_ready():
                print(f"[INFO] P3a 模式匹配已启用：success_samples={prof.n} days={P3A_MATCH_DAYS}")
            else:
                print("[WARNING] P3a 模式匹配启用但样本不足：将返回默认 0.5 分")
        except Exception as e:  # noqa: BLE001
            p3a_matcher = None
            print(f"[WARNING] P3a 模式匹配初始化失败（将禁用）：{e}")

    if exchange is None:
        print("[INFO] 未配置币安 API Key，将使用公共 API 获取数据")
    else:
        print("[INFO] 已配置币安 API Key，将优先使用公共 API")

    print("[INFO] 全市场异动扫描器启动（按 Ctrl+C 停止）")
    print(f"   第一层扫描：每 {SCAN_INTERVAL_SECONDS} 秒扫描全市场")
    if SKIP_24H_DROP_PCT is not None:
        print(f"   Level 0 硬过滤：剔除 24h 跌幅 <= {SKIP_24H_DROP_PCT}% 的币种")
    else:
        print(f"   Level 0 硬过滤：未启用（完全依赖 Level 1 结构层判断）")
    print(f"   第二层精筛：每 {DEEP_SCAN_INTERVAL_SECONDS} 秒对异动币种做深度采集（含 Level 1 结构层分析）")
    print(f"   存储策略：Shadow Mode（宽进严出）- 宽松采集标准，严格交易标准")
    print(f"   - 数据采集：Top {STORE_TOP_COUNT} 异动 + 宽松条件（费率<0.001%, 涨幅>1%, Wick>40%）")
    print(f"   - 交易执行：仅 PERFECT 标签允许实盘交易")
    
    # V4.4 策略路由状态
    v44_enabled = os.environ.get("V44_ENABLED", "0") in ("1", "true", "True")
    v44_multiplier = os.environ.get("V44_POSITION_SIZE_MULTIPLIER", "1.0")
    if v44_enabled:
        print(f"[INFO] ✅ V4.4 策略路由已启用（灰度发布倍数: {v44_multiplier}x）")
    else:
        print(f"[INFO] ⚠️  V4.4 策略路由未启用（设置 V44_ENABLED=1 启用）")

    # Supabase 写入队列/worker
    write_queue: asyncio.Queue = asyncio.Queue(maxsize=WRITE_QUEUE_MAXSIZE)
    if supabase is not None:
        for _ in range(WRITE_WORKERS):
            asyncio.create_task(_supabase_write_worker(write_queue, supabase))
    else:
        print("[WARNING] Supabase 未连接：将只打印数据，不写入数据库。")
    
    # V4.3 持仓管理器初始化（V4.5: 支持配置热加载）
    v43_position_manager = None
    if V43_AVAILABLE and V43_ENABLED and V43PositionManager is not None:
        try:
            # V4.5: 使用配置管理器获取配置（支持热加载）
            v43_trader = None
            try:
                from binance_config_manager import get_config_manager
                from binance_trader import BinanceTrader
                
                config_manager = get_config_manager(supabase_client=supabase)
                # 强制刷新配置（避免使用旧缓存）
                config = config_manager.get_config(force_refresh=True)
                
                if config:
                    # 验证配置有效性
                    api_key = config.get("api_key", "")
                    api_secret = config.get("api_secret", "")
                    if not api_key or not api_secret:
                        print("[WARNING] 配置管理器返回的配置不完整，回退到环境变量")
                        config = None
                    elif len(api_secret) != 64:
                        print(f"[WARNING] Secret 长度异常: {len(api_secret)} 字符（应该是 64），可能解密失败")
                        print("[WARNING] 回退到环境变量")
                        config = None
                
                if config:
                    # 检查是否启用自动交易
                    enable_auto_trading = os.environ.get("ENABLE_AUTO_TRADING", "false").lower() in ("true", "1")
                    if enable_auto_trading:
                        try:
                            v43_trader = BinanceTrader(
                                api_key=config["api_key"],
                                api_secret=config["api_secret"],
                                testnet=config["testnet"],
                                leverage=config.get("leverage", 10),
                            )
                            print(f"[INFO] ✅ V4.5 币安交易器已初始化（自动交易已启用，杠杆 {config.get('leverage', 10)}x）")
                            print(f"[INFO] API Key: {config['api_key'][:10]}...{config['api_key'][-10:]} (测试网: {config['testnet']})")
                        except Exception as trader_error:
                            print(f"[ERROR] 币安交易器初始化失败: {trader_error}")
                            print("[WARNING] 将回退到环境变量")
                            config = None
                    else:
                        print("[INFO] ⚠️ V4.5 币安交易器未启用（ENABLE_AUTO_TRADING=false，仅模拟交易）")
                else:
                    # 回退到环境变量（向后兼容）
                    if BINANCE_API_KEY and BINANCE_API_SECRET:
                        enable_auto_trading = os.environ.get("ENABLE_AUTO_TRADING", "false").lower() in ("true", "1")
                        if enable_auto_trading:
                            try:
                                v43_trader = BinanceTrader()
                                print("[INFO] ✅ V4.3 币安交易器已初始化（从环境变量，自动交易已启用）")
                            except Exception as trader_error:
                                print(f"[ERROR] 从环境变量初始化交易器失败: {trader_error}")
                                print("[WARNING] 自动交易功能将不可用")
                    else:
                        print("[WARNING] 未找到币安 API 配置（数据库和环境变量都没有）")
            except ImportError:
                # 如果配置管理器不可用，回退到旧逻辑
                if BINANCE_API_KEY and BINANCE_API_SECRET:
                    try:
                        from binance_trader import BinanceTrader
                        enable_auto_trading = os.environ.get("ENABLE_AUTO_TRADING", "false").lower() in ("true", "1")
                        if enable_auto_trading:
                            v43_trader = BinanceTrader()
                            print("[INFO] ✅ V4.3 币安交易器已初始化（自动交易已启用）")
                    except Exception as e:
                        print(f"[WARNING] V4.3 币安交易器初始化失败: {e}")
            except Exception as e:
                print(f"[WARNING] V4.5 币安交易器初始化失败: {e}")
            
            v43_position_manager = V43PositionManager(
                supabase_client=supabase,
                exchange=exchange,
                trader=v43_trader,  # 传入交易器
            )
            # 加载现有持仓
            v43_position_manager.load_open_positions()
            print("[INFO] ✅ V4.3 持仓管理器已初始化")
            
            # V4.5: 启动持仓同步任务（后台运行）
            try:
                from binance_position_sync import get_position_sync
                # 使用全局已导入的 asyncio 模块，不要重新导入
                
                position_sync = get_position_sync(supabase_client=supabase, trader=v43_trader)
                
                async def sync_positions_periodically():
                    """定期同步持仓（每 5 分钟）"""
                    while True:
                        try:
                            await asyncio.sleep(300)  # 5 分钟
                            if v43_trader:  # 只在启用交易器时同步
                                result = position_sync.sync_positions()
                                if result.get("success"):
                                    print(f"[SYNC] 持仓同步完成: {result.get('synced_count', 0)} 个")
                        except Exception as e:
                            print(f"[WARNING] 持仓同步任务失败: {e}")
                
                # 启动后台任务
                asyncio.create_task(sync_positions_periodically())
                print("[INFO] ✅ V4.5 持仓同步任务已启动（每 5 分钟同步一次）")
            except Exception as e:
                print(f"[WARNING] V4.5 持仓同步任务启动失败: {e}")
                
        except Exception as e:
            print(f"[WARNING] V4.3 持仓管理器初始化失败: {e}")
            v43_position_manager = None

    # 缓存：当前异动币种列表 + 深度数据 + CVD 数据
    current_movers: list[tuple[str, float, str]] = []
    deep_data_cache: dict[str, dict[str, Any]] = {}  # {symbol: {price, funding, oi, ls, ...}}
    cvd_data_cache: dict[str, dict[str, Any]] = {}   # {ccxt_symbol: cvd_metrics}
    oi_series_cache: dict[str, list[tuple[float, float]]] = {}  # {binance_symbol: [(ts, oi_value), ...]}
    last_deep_scan_ts = 0.0
    last_cvd_update_ts = 0.0
    
    # 账户余额缓存（用于优化 API 调用，避免频繁请求）
    account_balance_cache = {
        "balance": 10000.0,  # 默认值
        "last_update": 0.0,  # 时间戳
        "update_interval": 30.0,  # 30 秒更新一次
    }

    # 限制并发，避免瞬时并发过高触发限流
    sem = asyncio.Semaphore(10)

    async def fetch_deep_metrics(symbol: str) -> tuple[str, dict] | None:
        """
        第二层：深度采集（OI + LS Ratio + 历史变化率 + Level 1 结构层分析）
        
        返回: (symbol, metrics) 或 None（如果被 Level 1 过滤掉）
        """
        async with sem:
            ccxt_symbol = binance_symbol_to_ccxt_symbol(symbol)
            
            # ========== Level 1 结构层分析（V4.2 分层漏斗）==========
            # 先获取 1h/4h OHLCV 数据，判断是否正在崩盘（P4_CRASHING）
            try:
                from whale_detector import analyze_structure_level_1
                
                ohlcv_1h = await asyncio.to_thread(lambda: fetch_klines_ohlcv(symbol, interval="1h", limit=10))
                ohlcv_4h = await asyncio.to_thread(lambda: fetch_klines_ohlcv(symbol, interval="4h", limit=10))
                
                if ohlcv_1h and ohlcv_4h:
                    level1_phase, level1_reason = analyze_structure_level_1(ohlcv_1h, ohlcv_4h)
                    
                    # 排除逻辑：正在崩盘（Falling Knife）直接丢弃，不进入后续处理
                    if level1_phase == "P4_CRASHING":
                        print(f"[INFO] {ccxt_symbol} 被 Level 1 过滤：{level1_reason}")
                        return None  # 返回 None 表示被过滤
                    
                    # 将 Level 1 结果存入 metrics（用于后续日志/存储）
                    level1_result = {"phase": level1_phase, "reason": level1_reason}
                else:
                    level1_result = None
            except ImportError:
                # whale_detector 未导入，跳过 Level 1 分析
                level1_result = None
            except Exception as e:  # noqa: BLE001
                # Level 1 分析失败不影响主流程，静默处理
                level1_result = None
                print(f"[WARNING] {symbol} Level 1 分析失败: {e}")
            
            # 获取快指标
            fast_data = await asyncio.to_thread(lambda: fetch_price_and_funding(ccxt_symbol, exchange))
            # 获取慢指标
            slow_data = await asyncio.to_thread(lambda: fetch_slow_metrics(ccxt_symbol, exchange))
            
            # 合并数据
            price = float(fast_data["price"])
            funding_rate = float(fast_data["funding_rate"])
            oi_value = slow_data.get("oi_value")
            ls_ratio = slow_data.get("ls_ratio")
            
            # 计算 1 小时变化率
            price_change = None
            oi_change = None
            # 优先使用币安公共 API 直接计算（避免“数据库尚无历史行”与 Windows socket 抖动导致的变化率缺失）
            price_change = await asyncio.to_thread(lambda: fetch_price_change_1h_via_klines(symbol))
            if oi_value is not None:
                oi_change = await asyncio.to_thread(lambda: fetch_oi_change_1h_via_open_interest_hist(symbol))

            # 若公共 API 失败，回退：使用 Supabase 历史行（有数据时更稳）
            if (price_change is None or oi_change is None) and supabase is not None and oi_value is not None:
                historical = await asyncio.to_thread(lambda: get_historical_data(supabase, ccxt_symbol))
                pc2, oc2 = calculate_changes(price, float(oi_value), historical)
                price_change = price_change if price_change is not None else pc2
                oi_change = oi_change if oi_change is not None else oc2
            
            metrics = {
                "price": price,
                "funding_rate": funding_rate,
                "oi_value": oi_value,
                "ls_ratio": ls_ratio,
                "price_change": price_change,
                "oi_change": oi_change,
                "_ts": time.time(),
            }
            
            # 将 Level 1 结果添加到 metrics（如果存在）
            if level1_result:
                metrics["level1_phase"] = level1_result["phase"]
                metrics["level1_reason"] = level1_result["reason"]
            
            return symbol, metrics

    async def fetch_cvd_metrics_for_symbol(binance_symbol: str) -> tuple[str, dict | None]:
        """
        使用 CVDAnalyzer 计算指定币种的 CVD 指标。

        这里的 symbol 传入为币安格式，如 TRBUSDT，内部会转换为 ccxt 格式 TRB/USDT。
        """
        async with sem:
            ccxt_symbol = binance_symbol_to_ccxt_symbol(binance_symbol)
            cvd_metrics = await cvd_analyzer.calculate_cvd_metrics(ccxt_symbol, limit=1000)
            return ccxt_symbol, cvd_metrics

    while True:
        loop_started = time.time()

        try:
            # ========== 第一层（粗筛）：全市场扫描 ==========
            all_tickers = await asyncio.to_thread(scan_all_markets_via_public_api)
            movers = await asyncio.to_thread(lambda: detect_movers(all_tickers, supabase))
            current_movers = movers

            if not movers:
                print("[INFO] 本轮未发现异动币种")
            else:
                top_preview_n = 5
                print(
                    f"[INFO] 发现 {len(movers)} 个异动币种（Top {top_preview_n}: "
                    f"{', '.join([m[0] for m in movers[:top_preview_n]])}）"
                )

            # ========== 第二层（精筛）：深度采集 ==========
            need_deep_scan = (time.time() - last_deep_scan_ts) >= DEEP_SCAN_INTERVAL_SECONDS
            need_cvd_update = (time.time() - last_cvd_update_ts) >= CVD_UPDATE_INTERVAL_SECONDS

            if need_deep_scan and movers:
                # 对 TOP 10 异动币种做深度采集
                mover_symbols = [m[0] for m in movers[:TOP_MOVERS_COUNT]]
                deep_results = await asyncio.gather(
                    *[fetch_deep_metrics(s) for s in mover_symbols],
                    return_exceptions=True
                )

                for r in deep_results:
                    if isinstance(r, Exception):
                        print(f"[WARNING] 深度采集失败: {r}")
                        continue
                    if r is None:
                        # 被 Level 1 过滤掉（P4_CRASHING），跳过
                        continue
                    symbol, data = r
                    deep_data_cache[symbol] = data

                    # 维护 OI 时间序列（用于 P3a 二次放量验证）
                    try:
                        oi_v = data.get("oi_value")
                        ts = float(data.get("_ts") or time.time())
                        if oi_v is not None:
                            series = oi_series_cache.get(symbol, [])
                            series.append((ts, float(oi_v)))
                            # 控制长度，避免无限增长（保留最近 20 个点）
                            if len(series) > 20:
                                series = series[-20:]
                            oi_series_cache[symbol] = series
                    except Exception:
                        pass

                last_deep_scan_ts = time.time()

            # 仅对 Top N 异动币种计算 CVD，避免过度消耗 API 权重
            if need_cvd_update and movers:
                top_for_cvd = [m[0] for m in movers[:STORE_TOP_COUNT]]
                cvd_results = await asyncio.gather(
                    *[fetch_cvd_metrics_for_symbol(s) for s in top_for_cvd],
                    return_exceptions=True
                )

                for r in cvd_results:
                    if isinstance(r, Exception):
                        print(f"[WARNING] CVD 计算失败: {r}")
                        continue
                    ccxt_symbol, cvd_metrics = r
                    if cvd_metrics:
                        cvd_data_cache[ccxt_symbol] = cvd_metrics

                last_cvd_update_ts = time.time()

            # ========== 第三层（存储）：条件写入 ==========
            for symbol, score, reason in movers:
                try:
                    ccxt_symbol = binance_symbol_to_ccxt_symbol(symbol)
                    
                    # 获取基础数据（从 ticker 或缓存）
                    ticker = all_tickers.get(symbol, {})
                    price = float(ticker.get("lastPrice", 0))
                    funding_rate = float(ticker.get("lastFundingRate", 0)) if "lastFundingRate" in ticker else None
                    
                    # 如果有深度数据，优先使用
                    deep = deep_data_cache.get(symbol, {})
                    if deep:
                        price = float(deep.get("price", price))
                        funding_rate = float(deep.get("funding_rate", funding_rate or 0.0))
                    
                    # 如果 funding_rate 还是 None，尝试获取
                    if funding_rate is None:
                        try:
                            funding_data = await asyncio.to_thread(
                                lambda: fetch_price_and_funding_via_public_api(symbol)
                            )
                            funding_rate = float(funding_data.get("funding_rate", 0.0))
                        except Exception:
                            funding_rate = 0.0

                    # 尝试获取24h价格变化（用于Shadow Mode宽松采集）
                    price_change_24h = None
                    try:
                        # 从deep_data_cache或ticker获取24h数据
                        ticker_data = deep.get("ticker_data")
                        if ticker_data and isinstance(ticker_data, dict):
                            if "raw" in ticker_data:
                                ticker_raw = ticker_data["raw"].get("ticker", {})
                                if ticker_raw and "priceChangePercent" in ticker_raw:
                                    price_change_24h = float(ticker_raw["priceChangePercent"])
                    except Exception:
                        pass  # 24h数据获取失败不影响主流程
                    
                    # 构建完整 metrics
                    metrics = {
                        "price": price,
                        "funding_rate": funding_rate,
                        "price_change_24h": price_change_24h,  # Shadow Mode 使用
                        "oi_value": deep.get("oi_value"),
                        "ls_ratio": deep.get("ls_ratio"),
                        "price_change": deep.get("price_change"),
                        "oi_change": deep.get("oi_change"),
                        # 来自 CVDAnalyzer 的指标（可能不存在）
                        "cvd_data": cvd_data_cache.get(ccxt_symbol),
                        # OI 序列（binance_symbol 作为 key）
                        "oi_series": oi_series_cache.get(symbol),
                    }

                    # ==================== V4 推断（提前写入 metrics，供 should_store / snapshot 使用） ====================
                    # 目的：哪怕 technical_signal 为空，也能按 phase/kill_zone/exit_score 触发写入 ai_training_data
                    try:
                        # 使用全局导入的 CVDAnalyzer，不再局部导入
                        from whale_detector import (
                            check_kill_zones,
                            compute_exit_clarity_score,
                            detect_phase,
                            is_oi_second_spike_confirmed,
                            PHASE_P2,
                            PHASE_P3A,
                        )

                        price_change = metrics.get("price_change")
                        oi_change = metrics.get("oi_change")
                        oi_series = metrics.get("oi_series")
                        cvd_data = metrics.get("cvd_data")

                        market_phase = "UNKNOWN"
                        kill_zone_signal = "NONE"
                        exit_clarity_score = None
                        cvd_intent = "NEUTRAL"
                        cvd_1h = None

                        if price_change is not None:
                            analyzer = CVDAnalyzer(None)
                            if cvd_data:
                                try:
                                    cvd_1h = float(cvd_data.get("cvd_1h", 0.0) or 0.0)
                                except Exception:
                                    cvd_1h = None
                                try:
                                    cvd_intent = analyzer.analyze_cvd_intent(float(price_change) / 100.0, cvd_data)
                                except Exception:
                                    cvd_intent = "NEUTRAL"

                            market_phase = detect_phase(
                                price_change_1h=price_change,
                                oi_change_1h=oi_change,
                                cvd_intent=cvd_intent,
                                cvd_1h=cvd_1h,
                                whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
                            )

                            # 强制验证：P3a 必须伴随 OI 二次放量（不满足则降级为 P2）
                            oi_second_spike_ok = is_oi_second_spike_confirmed(oi_series)
                            if market_phase == PHASE_P3A and not oi_second_spike_ok:
                                market_phase = PHASE_P2

                            price_breakout = True if float(price_change) > 2.0 else False
                            flash_crash = True if float(price_change) < -2.0 else False
                            oi_stable = True if (oi_change is None or float(oi_change) > -1.0) else False
                            kill_zone_signal = check_kill_zones(
                                funding_rate=funding_rate,
                                oi_change_1h=oi_change,
                                price_breakout=price_breakout,
                                cvd_intent=cvd_intent,
                                phase=market_phase,
                                flash_crash=flash_crash,
                                oi_stable=oi_stable,
                            ) or "NONE"

                            exit_clarity_score = compute_exit_clarity_score(
                                phase=market_phase,
                                kill_zone=kill_zone_signal,
                                funding_rate=funding_rate,
                                oi_change_1h=oi_change,
                                price_change_1h=price_change,
                                cvd_intent=cvd_intent,
                                oi_second_spike_confirmed=oi_second_spike_ok,
                            )

                        metrics["market_phase"] = market_phase or "UNKNOWN"
                        metrics["kill_zone_signal"] = kill_zone_signal or "NONE"
                        metrics["exit_clarity_score"] = exit_clarity_score
                    except Exception:
                        metrics["market_phase"] = metrics.get("market_phase") or "UNKNOWN"
                        metrics["kill_zone_signal"] = metrics.get("kill_zone_signal") or "NONE"
                        metrics["exit_clarity_score"] = metrics.get("exit_clarity_score")

                    # 判断是否应该存储到 ai_training_data（Shadow Mode 宽进严出）
                    # 注意：movers 是币安格式 symbol（如 LEVERUSDT），should_store 内部会做格式归一化
                    # 返回: (should_store, training_tag)
                    should_store, training_tag = should_store_to_ai_training(symbol, movers, metrics)

                    # 打印
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    extra_info = f"  [{reason}]"
                    if metrics.get("oi_value"):
                        extra_info += f"  OI={float(metrics['oi_value']):.1f}"
                    if metrics.get("ls_ratio"):
                        extra_info += f"  ls={float(metrics['ls_ratio']):.2f}"
                    print(f"[{ts}] {ccxt_symbol:12s} price={price:.4f} funding={funding_rate:.6f}{extra_info}")

                    # 写入 Supabase（条件存储）
                    if supabase is not None:
                        now_iso = datetime.now(timezone.utc).isoformat()
                        
                        ai_row: dict | None = None
                        if should_store:
                            ai_row = _build_ai_training_row(ccxt_symbol, now_iso, metrics, supabase, exchange)

                            # AI 裁决（可选）：优先 DeepSeek，其次本地 LR
                            # 仅在 should_store 时裁决，避免无意义消耗
                            # 计算 P3a 模式匹配分数（不写库，仅作为 AI 输入/理由补充）
                            p3a_match_score = 0.5
                            if p3a_matcher is not None:
                                try:
                                    p3a_match_score = float(p3a_matcher.score(ai_row))
                                except Exception:
                                    p3a_match_score = 0.5

                            # 动态阈值：confidence_level 越高，阈值越高（更难放行）
                            dynamic_thr = float(AI_JUDGE_THRESHOLD)
                            if AI_DYNAMIC_THRESHOLD_ENABLED:
                                try:
                                    cl = ai_row.get("confidence_level")
                                    clv = float(cl) if cl is not None else 0.0
                                    boost = (clv / 100.0) * AI_DYNAMIC_THRESHOLD_MAX_BOOST
                                    dynamic_thr = min(0.95, max(0.05, dynamic_thr + boost))
                                except Exception:
                                    dynamic_thr = float(AI_JUDGE_THRESHOLD)

                            if deepseek_judge is not None:
                                try:
                                    now_ts = time.time()
                                    cached = deepseek_cache.get(ccxt_symbol)
                                    if cached and (now_ts - cached[0]) < DEEPSEEK_CACHE_SECONDS:
                                        ai_row.update(cached[1])
                                    else:
                                        # DeepSeek 输入允许带额外上下文（不写库）
                                        ai_features = dict(ai_row)
                                        ai_features["p3a_match_score"] = p3a_match_score
                                        ai_features["dynamic_threshold"] = dynamic_thr
                                        d = deepseek_judge.judge(ai_features)
                                        if d is not None:
                                            patch = {
                                                "ai_score": d.ai_score,
                                                "ai_allowed": d.ai_allowed,
                                                "ai_reason": d.ai_reason,
                                                "ai_version": d.ai_version,
                                            }
                                            ai_row.update(patch)
                                            deepseek_cache[ccxt_symbol] = (now_ts, patch)
                                except Exception:
                                    pass

                            # DeepSeek 未命中/未配置时：回退本地模型
                            if ai_judge is not None and ai_row.get("ai_score") is None:
                                try:
                                    ai_features = dict(ai_row)
                                    ai_features["p3a_match_score"] = p3a_match_score
                                    ai_features["dynamic_threshold"] = dynamic_thr
                                    res = ai_judge.predict(ai_features)
                                    if res is not None:
                                        ai_row["ai_score"] = res.ai_score
                                        ai_row["ai_allowed"] = res.ai_allowed
                                        ai_row["ai_reason"] = res.ai_reason
                                        ai_row["ai_version"] = res.ai_version
                                except Exception:
                                    pass

                            # 动态阈值后处理：用 dynamic_thr 重新裁决 allowed（不管来自 DeepSeek 还是本地 LR）
                            try:
                                if ai_row.get("ai_score") is not None:
                                    s = float(ai_row.get("ai_score"))
                                    base_allowed = bool(ai_row.get("ai_allowed"))
                                    eff_thr = dynamic_thr
                                    # 轻量“模式匹配加成”：当 p3a_match_score 很高时，允许少量降低阈值（最多 -0.05）
                                    if p3a_match_score >= 0.75:
                                        eff_thr = max(0.05, dynamic_thr - 0.05)
                                    ai_row["ai_allowed"] = bool(base_allowed and (s >= eff_thr))
                                    r0 = str(ai_row.get("ai_reason") or "")
                                    ai_row["ai_reason"] = (
                                        f"{r0} | dyn_thr={dynamic_thr:.2f}"
                                        f" p3a_match={p3a_match_score:.2f}"
                                        f" eff_thr={eff_thr:.2f}"
                                    )
                            except Exception:
                                pass

                            # 持久化字段：用于前端展示/回测（已做 schema 扩展）
                            try:
                                ai_row["p3a_match_score"] = float(p3a_match_score)
                            except Exception:
                                ai_row["p3a_match_score"] = None
                            try:
                                # 如果上面计算失败，eff_thr 可能未定义；兜底用 dynamic_thr
                                ai_row["ai_effective_threshold"] = float(locals().get("eff_thr", dynamic_thr))
                            except Exception:
                                ai_row["ai_effective_threshold"] = None

                            # 仅用于验证：当 AI 字段写入成功时打印一行（不包含任何敏感信息）
                            if ai_row.get("ai_version") and ai_row.get("ai_score") is not None:
                                try:
                                    ai_version = ai_row.get('ai_version', 'unknown')
                                    ai_allowed = ai_row.get('ai_allowed', False)
                                    ai_score = float(ai_row.get('ai_score', 0))
                                    ai_reason_short = (ai_row.get('ai_reason') or '')[:60]
                                    phase = ai_row.get('market_phase', 'UNKNOWN')
                                    
                                    # 详细日志：显示 AI 分析结果
                                    print(
                                        f"[DEEPSEEK] {ccxt_symbol:12s} | "
                                        f"score={ai_score:.2f} | "
                                        f"allowed={ai_allowed} | "
                                        f"phase={phase} | "
                                        f"reason={ai_reason_short}"
                                    )
                                except Exception:
                                    pass

                            await write_queue.put({
                                "op": "insert",
                                "table": "ai_training_data",
                                "row": ai_row
                            })
                            
                            # ========== V4.3 集成：计算分数并写入 trade_scores_v43 ==========
                            if V43_AVAILABLE and V43_ENABLED:
                                try:
                                    from v43_collector_integration import process_v43_trading_decision, build_v43_trade_score_row
                                    from v43_weight_manager import load_weights
                                    
                                    # 准备 metrics（从 ai_row 和 metrics 中提取）
                                    v43_metrics = {
                                        "funding_rate": ai_row.get("funding_rate") or metrics.get("funding_rate"),
                                        "ls_ratio": ai_row.get("long_short_ratio") or metrics.get("ls_ratio"),
                                        "oi_value": ai_row.get("oi_value") or metrics.get("oi_value"),
                                        "oi_change": ai_row.get("oi_change_1h") or metrics.get("oi_change"),
                                        "price_change": ai_row.get("price_change_1h") or metrics.get("price_change"),
                                        "cvd_data": metrics.get("cvd_data"),
                                        "oi_series": metrics.get("oi_series"),
                                        "phase_4h": ai_row.get("phase_4h") or metrics.get("phase_4h"),
                                        "phase_1h": ai_row.get("phase_1h") or metrics.get("phase_1h"),
                                        "phase_age_candles": ai_row.get("phase_age_candles") or metrics.get("phase_age_candles"),
                                        "atr_value": ai_row.get("atr_value") or metrics.get("atr_value"),
                                        "highs_1h": metrics.get("highs_1h"),
                                        "closes_1h": metrics.get("closes_1h"),
                                        "ohlcv_15m": metrics.get("ohlcv_15m"),
                                        "prices": metrics.get("prices"),
                                    }
                                    
                                    # 处理 V4.3 交易决策
                                    v43_weights = load_weights()
                                    v43_features, v43_score_result, v43_decision_result = process_v43_trading_decision(
                                        symbol=ccxt_symbol,
                                        price=price,
                                        metrics=v43_metrics,
                                        weights=v43_weights,
                                        supabase_client=supabase,  # 传递 supabase 客户端用于查询持仓
                                    )
                                    
                                    # 构建 trade_scores_v43 行
                                    v43_score_row = build_v43_trade_score_row(
                                        symbol=ccxt_symbol,
                                        features=v43_features,
                                        score_result=v43_score_result,
                                        decision_result=v43_decision_result,
                                        weights=v43_weights,
                                    )
                                    
                                    # 写入 trade_scores_v43 表
                                    await write_queue.put({
                                        "op": "insert",
                                        "table": "trade_scores_v43",
                                        "row": v43_score_row
                                    })
                                    
                                    # 打印 V4.3/V4.4 决策日志（修复：即使 should_trade=False 也显示分数）
                                    final_score = v43_score_result.get("final_score", 0.0)
                                    should_trade = v43_decision_result.get("should_trade", False)
                                    block_reason = v43_decision_result.get("block_reason", "")
                                    
                                    # 检查 V4.4 策略路由是否启用
                                    strategy_id = v43_decision_result.get("strategy_id")
                                    side = v43_decision_result.get("side", "LONG")
                                    strategy_score = v43_decision_result.get("strategy_score")
                                    v44_enabled = os.environ.get("V44_ENABLED", "0") in ("1", "true", "True")
                                    
                                    # 显示各维度分数（用于调试）
                                    structure_score = v43_score_result.get("structure_score", 0.0)
                                    volatility_score = v43_score_result.get("volatility_score", 0.0)
                                    sentiment_score = v43_score_result.get("sentiment_score", 0.0)
                                    manipulation_score = v43_score_result.get("manipulation_score", 0.0)
                                    
                                    # 获取阶段信息
                                    phase = v43_features.get("phase", "N/A")
                                    
                                    # V4.4 策略路由日志（如果启用且有策略）
                                    if v44_enabled and strategy_id and strategy_id != "WAIT":
                                        # 如果没有单独的 strategy_score，则使用最终分数 *100 展示
                                        if isinstance(strategy_score, (int, float)):
                                            display_score = float(strategy_score)
                                        else:
                                            display_score = float(final_score) * 100.0

                                        print(
                                            f"[V4.4] {ccxt_symbol:15s} | "
                                            f"Strategy: {strategy_id:8s} | "
                                            f"Score: {display_score:5.1f} | "
                                            f"Side: {side:5s} | "
                                            f"{v43_decision_result.get('reason', '')[:60]}"
                                        )
                                    
                                    if should_trade:
                                        # 交易信号：完整显示
                                        version_tag = "[V4.4]" if (v44_enabled and strategy_id) else "[V4.3]"
                                        print(
                                            f"{version_tag} {ccxt_symbol:12s} | "
                                            f"score={final_score*100:5.1f} | "
                                            f"decision=✅ TRADE | "
                                            f"结构={structure_score*100:4.1f} 波动={volatility_score*100:4.1f} 情绪={sentiment_score*100:4.1f} 操控={manipulation_score*100:4.1f} | "
                                            f"phase={phase} | "
                                            f"reason={v43_decision_result.get('reason', '')[:50]}"
                                        )
                                        
                                        # ========== 自动下单逻辑 ==========
                                        if v43_position_manager:
                                            try:
                                                # 获取账户余额（使用缓存机制，避免频繁调用 API）
                                                current_time = time.time()
                                                last_update = account_balance_cache.get("last_update", 0.0)
                                                update_interval = account_balance_cache.get("update_interval", 30.0)
                                                
                                                # 如果缓存过期或不存在，更新余额
                                                if v43_trader and (current_time - last_update >= update_interval):
                                                    try:
                                                        # 使用 BinanceTrader 的 fetch_balance 方法（测试网时会使用直接 API 调用）
                                                        balance = v43_trader.fetch_balance()
                                                        usdt_info = balance.get("USDT") or balance.get("USDT:USDT") or {}
                                                        new_balance = float(usdt_info.get("total", 10000.0))
                                                        account_balance_cache["balance"] = new_balance
                                                        account_balance_cache["last_update"] = current_time
                                                        if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                                                            print(f"[DEBUG] 账户余额已更新: {new_balance:.2f} USDT")
                                                    except Exception as balance_error:
                                                        # 余额获取失败，使用缓存值或默认值
                                                        if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                                                            print(f"[DEBUG] 余额获取失败，使用缓存值: {balance_error}")
                                                
                                                # 使用缓存的余额
                                                account_balance = account_balance_cache.get("balance", 10000.0)
                                                
                                                # 获取 ATR 值（确保不为 None）
                                                atr_value = v43_features.get("atr") or v43_features.get("atr_1h") or 0.0
                                                if atr_value == 0.0 or atr_value is None:
                                                    atr_value = v43_metrics.get("atr_value") or 0.0
                                                # 确保 atr_value 是 float 类型且不为 None
                                                if atr_value is None:
                                                    atr_value = 0.0
                                                atr_value = float(atr_value)
                                                
                                                # 执行开仓
                                                position = v43_position_manager.open_position(
                                                    symbol=ccxt_symbol,
                                                    side=v43_decision_result.get("side", "LONG"),
                                                    entry_price=price,
                                                    features=v43_features,
                                                    decision_result=v43_decision_result,
                                                    account_balance=account_balance,
                                                    atr_value=atr_value,
                                                    write_queue=write_queue,
                                                )
                                                
                                                if position:
                                                    print(f"[V4.3] ✅ 自动开仓成功: {ccxt_symbol} {v43_decision_result.get('side')} @ {price}")
                                                else:
                                                    print(f"[WARNING] 自动开仓失败: {ccxt_symbol}（可能已有持仓或计算失败）")
                                            except Exception as trade_error:
                                                print(f"[ERROR] 自动开仓异常: {ccxt_symbol} - {trade_error}")
                                                if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                                                    import traceback
                                                    traceback.print_exc()
                                        else:
                                            if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                                                print(f"[DEBUG] 持仓管理器未初始化，跳过自动下单: {ccxt_symbol}")
                                    else:
                                        # 非交易信号：显示分数和拦截原因（用于调试）
                                        # 只在调试模式或分数 > 0 时显示（避免刷屏）
                                        if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True") or final_score > 0.0:
                                            decision_status = "❌ BLOCKED" if block_reason else "⏸️ SKIP"
                                            version_tag = "[V4.4]" if (v44_enabled and strategy_id) else "[V4.3]"
                                            print(
                                                f"{version_tag} {ccxt_symbol:12s} | "
                                                f"score={final_score*100:5.1f} | "
                                                f"decision={decision_status} | "
                                                f"结构={structure_score*100:4.1f} 波动={volatility_score*100:4.1f} 情绪={sentiment_score*100:4.1f} 操控={manipulation_score*100:4.1f} | "
                                                f"phase={phase}"
                                                + (f" | block={block_reason[:30]}" if block_reason else "")
                                            )
                                except ImportError as e:
                                    # 导入错误：可能是模块不存在或路径问题
                                    print(f"[WARNING] V4.3 模块导入失败: {e}")
                                    print(f"[WARNING] 将跳过 V4.3 处理，继续使用 V4.2 逻辑")
                                except Exception as e:  # noqa: BLE001
                                    # V4.3 处理失败不影响主流程
                                    error_type = type(e).__name__
                                    error_msg = str(e)
                                    print(f"[WARNING] V4.3 处理失败 ({error_type}): {error_msg[:200]}")
                                    # 仅在调试模式打印完整 traceback
                                    if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                                        import traceback
                                        traceback.print_exc()
                            
                            print(f"[INFO] ✅ 已存储 {ccxt_symbol} 到 ai_training_data（异动/Whale Alert）")
                        else:
                            # 调试：确认是否由于 symbol 格式/规则导致本轮不写入
                            pass

                        # 快照：所有异动币种都更新（队列满允许丢弃），并带上 V4/AI 展示字段
                        snapshot_metrics = {
                            "price": price,
                            "funding_rate": funding_rate,
                            "ls_ratio": metrics.get("ls_ratio"),
                            "price_change": metrics.get("price_change"),
                            "oi_change": metrics.get("oi_change"),
                            # 展示字段取自 ai_row（若有）或 metrics
                            "market_phase": (ai_row.get("market_phase") if ai_row else None) or metrics.get("market_phase") or "UNKNOWN",
                            "kill_zone_signal": (ai_row.get("kill_zone_signal") if ai_row else None) or metrics.get("kill_zone_signal") or "NONE",
                            "exit_clarity_score": ai_row.get("exit_clarity_score") if ai_row else metrics.get("exit_clarity_score"),
                            "confidence_level": ai_row.get("confidence_level") if ai_row else metrics.get("confidence_level"),
                            "ai_score": ai_row.get("ai_score") if ai_row else None,
                            "ai_allowed": ai_row.get("ai_allowed") if ai_row else None,
                            "ai_reason": ai_row.get("ai_reason") if ai_row else None,
                            "ai_version": ai_row.get("ai_version") if ai_row else None,
                            "p3a_match_score": ai_row.get("p3a_match_score") if ai_row else None,
                            "ai_effective_threshold": ai_row.get("ai_effective_threshold") if ai_row else None,
                        }
                        snapshot_row = _build_snapshot_row(ccxt_symbol, now_iso, snapshot_metrics)
                        safe_enqueue(write_queue, {
                            "op": "upsert",
                            "table": "market_snapshot",
                            "row": snapshot_row,
                            "on_conflict": "symbol"
                        }, symbol=ccxt_symbol, table="market_snapshot")

                except Exception as e:  # noqa: BLE001
                    print(f"[ERROR] {symbol} 处理出错：{e}")
                    traceback.print_exc()
                    continue

        except KeyboardInterrupt:
            # 用户中断（Ctrl+C），正常退出
            print("\n[INFO] 收到中断信号，正在安全退出...")
            break
        except Exception as e:  # noqa: BLE001
            # 主循环异常：打印错误但继续运行
            print(f"[ERROR] 主循环出错：{type(e).__name__}: {e}")
            traceback.print_exc()
            # 等待一段时间后继续，避免快速循环错误
            await asyncio.sleep(5)

        # ========== V4.3 持仓更新（定期同步）==========
        if v43_position_manager and V43_ENABLED:
            try:
                # 每 60 秒同步一次持仓状态
                current_time = time.time()
                if not hasattr(main_loop, "_last_position_sync"):
                    main_loop._last_position_sync = current_time
                
                if current_time - main_loop._last_position_sync >= 60:
                    # 加载所有持仓
                    open_positions = v43_position_manager.load_open_positions()
                    
                    # 更新每个持仓
                    for symbol, position in open_positions.items():
                        try:
                            # 获取当前价格（使用 ticker）
                            binance_symbol = symbol_to_binance_symbol(symbol)
                            try:
                                ticker = exchange.fetch_ticker(binance_symbol) if exchange else None
                                current_price = float(ticker["last"]) if ticker and "last" in ticker else None
                            except Exception:
                                current_price = None
                            
                            if current_price:
                                # 获取 ATR（需要 K 线数据）
                                ohlcv_15m = fetch_klines_ohlcv(binance_symbol, interval="15m", limit=20)
                                current_atr = None
                                if ohlcv_15m and len(ohlcv_15m) >= 14:
                                    try:
                                        from v41_risk_manager import calculate_atr
                                        highs = [c["high"] for c in ohlcv_15m[-20:]]
                                        lows = [c["low"] for c in ohlcv_15m[-20:]]
                                        closes = [c["close"] for c in ohlcv_15m[-20:]]
                                        current_atr = calculate_atr(highs, lows, closes)
                                    except Exception:
                                        pass
                                
                                if current_atr:
                                    # 获取当前阶段（从 market_snapshot 或重新计算）
                                    current_phase = position.get("phase", "P1_NO_WHALE")
                                    current_phase_age = position.get("phase_age", 0)
                                    
                                    # 更新持仓
                                    v43_position_manager.update_position(
                                        symbol=symbol,
                                        current_price=current_price,
                                        current_atr=current_atr,
                                        current_phase=current_phase,
                                        current_phase_age=current_phase_age,
                                        ohlcv_15m=ohlcv_15m,
                                        write_queue=write_queue,
                                    )
                        except Exception as e:
                            print(f"[WARNING] 更新持仓失败 ({symbol}): {e}")
                    
                    main_loop._last_position_sync = current_time
            except Exception as e:
                print(f"[WARNING] V4.3 持仓同步失败: {e}")
        
        # 控制扫描节拍：每 1 秒一轮（按耗时补差）
        elapsed = time.time() - loop_started
        await asyncio.sleep(max(0.0, SCAN_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    # V4.2 升级：启动 AI 学习循环（后台任务）
    import threading
    
    def start_learning_loop():
        """在后台线程中启动 AI 学习循环"""
        try:
            # 延迟导入，避免循环依赖
            time.sleep(5)  # 等待主循环初始化完成
            
            # 确保 scripts 目录在路径中
            scripts_dir = os.path.dirname(os.path.abspath(__file__))
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            
            # 导入学习循环模块（因为 collector.py 在 scripts/ 目录下，可以直接导入）
            from ai_learning_loop import AILearningLoop
            # 注意：使用全局已导入的 asyncio 模块，不要重新导入
            
            # 创建新的事件循环（用于后台线程）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 创建学习循环实例
            learning_loop = AILearningLoop(
                tuning_interval_hours=int(os.environ.get("AI_LEARNING_INTERVAL_HOURS", "6")),
                min_data_points=int(os.environ.get("AI_LEARNING_MIN_DATA_POINTS", "100")),
                min_trades=int(os.environ.get("AI_LEARNING_MIN_TRADES", "10")),
            )
            
            # 运行学习循环
            loop.run_until_complete(learning_loop.run_loop())
        except ImportError as e:
            print(f"[WARNING] AI 学习循环模块未找到，跳过自动学习功能: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"[WARNING] AI 学习循环启动失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 检查是否启用自动学习
    ai_learning_enabled = os.environ.get("AI_LEARNING_ENABLED", "1") in ("1", "true", "True")
    
    if ai_learning_enabled:
        # 启动后台学习循环线程
        learning_thread = threading.Thread(target=start_learning_loop, daemon=True, name="AI-Learning-Loop")
        learning_thread.start()
        print("[INFO] 🚀 AI 自动学习循环已启动（后台运行，每 6 小时自动调优）")
    else:
        print("[INFO] AI 自动学习循环已禁用（设置 AI_LEARNING_ENABLED=1 启用）")
    
    # 运行主采集循环
    asyncio.run(main_loop())


