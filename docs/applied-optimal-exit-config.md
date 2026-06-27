# 应用最优出场配置 — 240min 窗口 + SIGNAL_REVERSE 30min 最短门槛

> 2026-06-27 部署 · 依据 `docs/max-hold-scan-experiment.md`
> 性质: 改 paper **实战行为** (前向测试是真实观察)

## 改了什么

| 文件 | 项 | 旧 | 新 |
|---|---|---|---|
| `scripts/v5_params.py` | `DEFAULTS["v5_max_extensions"]` | 30 | **15** |
| `scripts/v5_params.py` | `DEFAULTS["v5_signal_reverse_min_minutes"]` (新加) | — | **30** |
| `scripts/v5_params.py` | `PARAM_META` 同步更新 + ENV 映射 `V5_SIGNAL_REVERSE_MIN_MINUTES` | — | 已加 |
| `scripts/v5_position_monitor.py` | `_max_extensions()` fallback | 30 | **15** |
| `scripts/v5_position_monitor.py` | `_signal_reverse_min_minutes()` 新函数 | — | 已加 |
| `scripts/v5_position_monitor.py` | `check_exit_triggers` 加 elapsed_min 门槛 | 无 | 已加 |

效果:
- **最长持仓** = soft_target(15min) × (1 + 15 ext) = **240 min (4h)**
- **SIGNAL_REVERSE** 在 entry 后前 30 min 屏蔽,30 min 后仍生效
- 历史 28 笔 SR 全部 < 30 min,所以新配置在历史样本上 = "完全关 SR";
  但保留**长仓真反转兜底**机制,信息上无损,完全可逆。

## 起点基线 (2026-06-27 部署前)

历史已平仓 52 笔:
- Net PF: 0.97
- 胜率: 44%
- avg PnL: -0.21%
- avg 持仓: 5.4 min (大量 SR 抢跑)
- **TP_HIT: 0 笔**
- SIGNAL_REVERSE: 54% / AI_TIMEBOX: 25%

Walk-forward backtest (240 档):
- Net PF 1.51 / 胜率 58% / avg R +0.24 / TP_HIT 45% / avg 持仓 134 min

## 期望观察 (新配置下前 ≥ 30 笔)

| 指标 | 起点 (历史) | 期望 (新配置) | 验收阈值 |
|---|---|---|---|
| TP_HIT 占比 | 0% | 25-45% | **≥ 10%** |
| Net PF | 0.97 | 1.0-1.5 | **≥ 1.0** |
| 胜率 | 44% | 50-58% | ≥ 50% |
| SIGNAL_REVERSE 占比 | 54% | < 10% | < 20% |
| AI_TIMEBOX 占比 | 25% | < 15% | < 20% |
| avg 持仓 | 5.4 min | 80-150 min | > 30 min |

**核心问题**: paper 起点 avg PnL -0.21% vs backtest 240 档 +0.24%——这中间 0.45% 的差距能不能被这次改动抹平。

## 中期 / 末期检查 (cron 已设)

- 2026-06-30 09:03: 中期检查 (3 天) — extension_count > 3 出现?TP_HIT 出现?
- 2026-07-04 09:07: 一周复盘 — 完整 verdict 报告
- ⚠ Cron job `session-only`,Claude 会话关闭就丢

## 一键回滚

如果新配置数据明显恶化,**不需要 git revert**——只改 DB:

```bash
# 回到旧行为 (max_ext=30, SR 立即生效)
sqlite3 data/rabbit_hunter.db "
  INSERT INTO system_settings(key, value) VALUES ('v5_max_extensions', '30');
  INSERT INTO system_settings(key, value) VALUES ('v5_signal_reverse_min_minutes', '0');
"
# 或重启 docker 让缓存过期
```

或更彻底:

```bash
# 改回 default 即可,无 DB 覆盖时直接走 default
git revert HEAD
docker compose restart api collector
```

## 不动的代码 (按指令)

- ❌ backtest 默认值 (`MAX_HOLD_MINUTES=480`)
- ❌ 进场逻辑 (`v5_strategy.decide`)
- ❌ 风控宪法 (`risk_constitution.py`)
- ❌ 仓位计算 (`v5_risk_calculator.plan`)
- ❌ 之前 4 个 HIGH 修复 commit (本次单独 commit)
