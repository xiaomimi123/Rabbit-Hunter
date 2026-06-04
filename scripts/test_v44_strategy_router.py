"""
V4.4 策略路由测试脚本

测试策略路由逻辑是否正确工作
"""

import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

# 启用 V4.4
os.environ["V44_ENABLED"] = "1"

try:
    from v44_strategy_router import route_strategy, StrategyResult, calculate_whale_activity
    from v43_score_calculator import aggregate_score
    from v43_weight_manager import load_weights
except ImportError as e:
    print(f"[ERROR] 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] 初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 80)
print("V4.4 策略路由测试")
print("=" * 80)
print()

# 加载权重
weights = load_weights()

# 测试用例 1: Sniffer 策略（P2 + OI上升）
print("1️⃣ 测试 Sniffer 策略（P2 + OI上升）")
print("-" * 80)

features_sniffer = {
    "phase": "P2_ACCUMULATION",
    "phase_age": 100,
    "htf_align": 1,  # 多周期对齐
    "oi_change": 0.16,  # 16% OI 上升
    "volume_spike": 2.5,
    "funding": -0.0003,
    "ls_ratio": 1.5,
    "atr": 0.0001,
    "atr_expand": 0.1,
    "range_left": 0.015,  # 1.5%（会被 LOW_EXPECTED_RETURN 拦截）
    "lower_wick": 0.3,
    "liq_cluster": 0.5,
    "current_price": 0.0031,
    "price": 0.0031,
}

try:
    score_result_sniffer = aggregate_score(features_sniffer, weights)
    strategy_result_sniffer = route_strategy(
        features=features_sniffer,
        score_result=score_result_sniffer,
        block_reason="LOW_EXPECTED_RETURN",
    )
except Exception as e:
    print(f"[ERROR] Sniffer 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"特征: P2阶段, OI上升16%, 爆量2.5x")
print(f"策略: {strategy_result_sniffer.id}")
print(f"方向: {strategy_result_sniffer.side}")
print(f"分数: {strategy_result_sniffer.score:.1f}")
print(f"置信度: {strategy_result_sniffer.confidence:.2f}")
print(f"原因: {strategy_result_sniffer.reason}")
if strategy_result_sniffer.risk_profile:
    print(f"风险配置: 仓位={strategy_result_sniffer.risk_profile.get('position_size', 0)}x, 止损={strategy_result_sniffer.risk_profile.get('stop_loss_atr_multiplier', 0)}x ATR")
else:
    print(f"风险配置: 无")
print()

# 测试用例 2: Sniper 策略（P3A + 高结构分）
print("2️⃣ 测试 Sniper 策略（P3A + 高结构分）")
print("-" * 80)

features_sniper = {
    "phase": "P3A_PUMP_START",
    "phase_age": 10,
    "htf_align": 1,
    "oi_change": 0.05,
    "volume_spike": 3.0,
    "funding": -0.0005,
    "ls_ratio": 1.2,
    "atr": 0.0001,
    "atr_expand": 0.2,
    "range_left": 0.05,  # 5%（足够空间）
    "lower_wick": 0.2,
    "liq_cluster": 0.6,
    "current_price": 0.0031,
    "price": 0.0031,
}

try:
    score_result_sniper = aggregate_score(features_sniper, weights)
    strategy_result_sniper = route_strategy(
        features=features_sniper,
        score_result=score_result_sniper,
        block_reason="",
    )
except Exception as e:
    print(f"[ERROR] Sniper 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"特征: P3A阶段, 结构分高, 预期收益5%")
print(f"策略: {strategy_result_sniper.id}")
print(f"方向: {strategy_result_sniper.side}")
print(f"分数: {strategy_result_sniper.score:.1f}")
print(f"置信度: {strategy_result_sniper.confidence:.2f}")
print(f"原因: {strategy_result_sniper.reason}")
if strategy_result_sniper.risk_profile:
    print(f"风险配置: 仓位={strategy_result_sniper.risk_profile.get('position_size', 0)}x, 止损={strategy_result_sniper.risk_profile.get('stop_loss_atr_multiplier', 0)}x ATR")
else:
    print(f"风险配置: 无")
print()

# 测试用例 3: Vulture 策略（P3B + OI下降）
print("3️⃣ 测试 Vulture 策略（P3B + OI下降）")
print("-" * 80)

features_vulture = {
    "phase": "P3B_PUMP_LATE",
    "phase_age": 50,
    "htf_align": 0,
    "oi_change": -0.06,  # -6% OI 下降（必须 < -0.05 才能触发）
    "volume_spike": 1.5,
    "funding": 0.0001,
    "ls_ratio": 1.8,
    "atr": 0.0001,
    "atr_expand": 0.0,
    "range_left": 0.01,  # 1%（会被 LOW_EXPECTED_RETURN 拦截）
    "lower_wick": 0.1,
    "liq_cluster": 0.3,
    "current_price": 0.0031,
    "price": 0.0031,
}

try:
    score_result_vulture = aggregate_score(features_vulture, weights)
    print(f"[DEBUG] Vulture 测试 - OI变化: {features_vulture['oi_change']:.2%}, block_reason: LOW_EXPECTED_RETURN")
    strategy_result_vulture = route_strategy(
        features=features_vulture,
        score_result=score_result_vulture,
        block_reason="LOW_EXPECTED_RETURN",
    )
except Exception as e:
    print(f"[ERROR] Vulture 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"特征: P3B阶段, OI下降6%, 被LOW_EXPECTED_RETURN拦截")
print(f"策略: {strategy_result_vulture.id}")
print(f"方向: {strategy_result_vulture.side}")
print(f"分数: {strategy_result_vulture.score:.1f}")
print(f"置信度: {strategy_result_vulture.confidence:.2f}")
print(f"原因: {strategy_result_vulture.reason}")
if strategy_result_vulture.risk_profile:
    print(f"风险配置: 仓位={strategy_result_vulture.risk_profile.get('position_size', 0)}x, 止损={strategy_result_vulture.risk_profile.get('stop_loss_atr_multiplier', 0)}x ATR")
else:
    print(f"风险配置: 无（策略未触发）")
print()

# 测试用例 4: WAIT（P1 阶段）
print("4️⃣ 测试 WAIT（P1 阶段）")
print("-" * 80)

features_wait = {
    "phase": "P1_NO_WHALE",
    "phase_age": 100,
    "htf_align": 0,
    "oi_change": 0.01,
    "volume_spike": 1.0,
    "funding": 0.0,
    "ls_ratio": 1.0,
    "atr": 0.0001,
    "atr_expand": 0.0,
    "range_left": 0.01,
    "lower_wick": 0.0,
    "liq_cluster": 0.0,
    "current_price": 0.0031,
    "price": 0.0031,
}

try:
    score_result_wait = aggregate_score(features_wait, weights)
    strategy_result_wait = route_strategy(
        features=features_wait,
        score_result=score_result_wait,
        block_reason="PHASE_NOT_ALLOWED",
    )
except Exception as e:
    print(f"[ERROR] WAIT 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"特征: P1阶段, 无庄家活动")
print(f"策略: {strategy_result_wait.id}")
print(f"方向: {strategy_result_wait.side}")
print(f"原因: {strategy_result_wait.reason}")
print()

# 测试用例 5: 庄家活动强度计算
print("5️⃣ 测试庄家活动强度计算")
print("-" * 80)

test_cases = [
    {"oi_change": 0.16, "volume_spike": 3.0, "funding": -0.0005, "ls_ratio": 1.5, "desc": "强信号（PTB/USDT类似）"},
    {"oi_change": 0.05, "volume_spike": 2.0, "funding": -0.0002, "ls_ratio": 1.2, "desc": "中等信号"},
    {"oi_change": 0.01, "volume_spike": 1.0, "funding": 0.0, "ls_ratio": 1.0, "desc": "弱信号"},
]

for i, case in enumerate(test_cases, 1):
    features_test = {
        "phase": "P2_ACCUMULATION",
        "oi_change": case["oi_change"],
        "volume_spike": case["volume_spike"],
        "funding": case["funding"],
        "ls_ratio": case["ls_ratio"],
    }
    whale_activity = calculate_whale_activity(features_test)
    print(f"  {i}. {case['desc']}")
    print(f"     OI变化: {case['oi_change']:.2%}, 爆量: {case['volume_spike']:.1f}x, 费率: {case['funding']:.4f}, LS: {case['ls_ratio']:.2f}")
    print(f"     庄家活动强度: {whale_activity:.2f} {'✅' if whale_activity > 0.8 else '⚠️' if whale_activity > 0.5 else '❌'}")
    print()

print("=" * 80)
print("测试完成")
print("=" * 80)
print()
print("📝 说明:")
print("  - Sniffer: 应该在 P2 + OI上升>5% 时触发")
print("  - Sniper: 应该在 P3A + 结构分>60 时触发")
print("  - Vulture: 应该在 P3B/P4 + OI下降>5% + 被拒 时触发")
print("  - WAIT: 其他情况")

