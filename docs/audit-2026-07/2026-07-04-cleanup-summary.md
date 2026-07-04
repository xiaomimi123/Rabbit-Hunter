# Audit 2026-07 · 清理完成总结报告

> **日期**: 2026-07-04
> **状态**: 全部 21 audit findings 修完 + push origin/main;3 pre-existing SIGNAL_REVERSE test 清理完成
> **总提交**: 43 commits (21 batches × spec/plan/impl 组合)

---

## 一、TL;DR

| 项 | 结果 |
|---|---|
| Audit findings 覆盖率 | **21/21 (100%)** — 5 P0 + 11 P1 + 5 P2 |
| SIGNAL_REVERSE test 清理 | ✅ 3 tests 修复, 18/18 v5_position_monitor 全绿 |
| Batches 执行 | **21 batches** (每 finding 一批, SDD subagent-driven) |
| 新增测试 | 60+ tests (backend + frontend) |
| 已有 tests 回归 | 0 (每批都跑邻近 regression) |
| 生产代码风险 | 每批独立 rollback 可能, plan/spec 完整留档 |
| CI 剩余 debt | 4 pre-existing failures (3 deepseek_adapter + 1 scoring_pipeline), **不在 audit scope** |

---

## 二、全景表

### P0 (LIVE 关键路径, Batches 1-5)

| # | Finding | Batch | Commit | 一句话 |
|---|---|---|---|---|
| F4 | V5PositionManager.create_order 方法根本不存在 | 1 | (Batch 1) | LIVE 开仓从没成功过, 修好后能真正下单 |
| F5 | LIVE 监控在 live_pm=None 时静默停止 | 2 | (Batch 2) | 监控自愈 + 发 ws `monitor_degraded` 事件 |
| F1 | SL_TP_FAIL_OPEN import-time 常量, UI 改无效 | 3 | (Batch 3) | 抽 settings_db helper, DB 值即时生效 |
| F2 | close_position 吞 broker 失败仍标 CLOSED | 4 | (Batch 4) | 按 error_kind 分 4 支路径 |
| F3 | LIVE 余额拉失败以 paper 余额代入风控 | 5 | (Batch 5) | 返 None + scorer 写 BALANCE_UNAVAILABLE |

### P1 (Batches 6-16)

| # | Finding | Batch | Commit | 一句话 |
|---|---|---|---|---|
| F10 | V5Scorer.run 广谱 catch 静默丢 item | 6 | `9eabf21` | 打日志 + 发 ws `scorer_error` |
| F8 | get_param() 吞 DB 错无日志 | 7 | `49206fb` | except pass → print WARN |
| F6 | walkforward LOCAL_DB_PATH 命名分裂 | 8 | `99aa5a5` | 统一 DB_PATH env, 3 tests |
| F7 | preview 端点从 0 行 ai_training_data 读胜率 | 9 | `d27dfc6` | 改 paper_trades JOIN, + data_source/sample_n |
| F9 | walkforward daemon 僵尸 job 卡 running | 10 | `f4fb75d` | 模块加载清 >2h 僵尸为 failed |
| F11 | max_concurrent 检查与 open_position 不原子 | 11 | `c7b2ce7` | BEGIN IMMEDIATE + 二次 count (paper 侧) |
| F12 | v5_position_close 端点不支持 LIVE 分支 | 12 | `ed39f0c` | 双表查询, `mode: paper/live` + 502/503 分层 |
| F13 | manual-order execute 绕过所有 M3 铁律 | 13 | `d32fc43` | 4 层守卫 (SHORT/setup/daily/per_trade) |
| F14 | LIVE exit_price 用 monitor tick 价非成交价 | 14 | `de246f9` | 用 broker fill price + error_context 标 source |
| F15 | useV5ActivePositions Promise.all 任一失败全暗 | 15 | `d7b9de7` | allSettled + live_error/paper_error 字段 |
| F16 | Dashboard 24h PnL 仅来自 paper_trades | 16 | `909c944` | 5 路 allSettled + union merge |

### P2 (Batches 17-21)

| # | Finding | Batch | Commit | 一句话 |
|---|---|---|---|---|
| F17 | _resolve_leverage 静默吞异常 | 17 | `995e0a2` | 同 F8 模式, print WARN + 1 test |
| F18 | SettingsPage 同时活仓上限 TextInput 无 onChange | 18 | `728aa4d` + `21fa2b2` | 后端 v5_max_concurrent + 前端受控 state |
| F19 | BacktestPage useEffect 缺 selectedReport 依赖 | 19 | `326e26e` | deps 补 selectedReport (lint 合规) |
| F20 | Dashboard 客户端做 2500 行聚合 | 20 | `a024b9f` + `9a816ab` | 新后端 /dashboard/summary, 前端单端点 |
| F21 | useV5WebSocket 断开重连后不 invalidate | 21 | `f6de823` | 重连时 invalidate active/dashboard |

### SIGNAL_REVERSE test 清理

| 描述 | Commit | 修法 |
|---|---|---|
| 3 SR tests 因 entry_time=now-10min < 门槛 30min → check_exit_triggers 返 None | `4aa22bb` | `_open_position` 加 `entry_age_min` 参数, 3 tests 传 40 |

---

## 三、建立的模式(可复用于未来 fix)

### 后端模式

1. **静默 catch → print WARN 模板** (F8 → F17 → F10 复用同款):
   ```python
   except Exception as e:
       print(f"[Module] 操作 失败,回退到 fallback: {type(e).__name__}: {e}")
   ```

2. **ws 观测事件模板** (F5 建立, F10 复用):
   ```python
   _enqueue_ws(self.db_path, {"type": "*_error", "error": ..., "symbol": ...})
   ```

3. **error_kind 分层 catch** (F2 建立, F12 复用):
   - broker success → CLOSED
   - broker PERMANENT → CLOSED (compensating)
   - broker RETRYABLE → 保持 OPEN
   - broker UNKNOWN → ERROR_RECONCILE_NEEDED

4. **error_context 附加 source 标签** (F14 建立):
   - `"broker_fill" / "monitor_tick" / "monitor_tick_permanent"` 让审计层能识别 exit_price 可信度

5. **BEGIN IMMEDIATE + 二次校验** (F11, TOCTOU 修复模式):
   - 悲观锁内 count → 判 → INSERT → COMMIT
   - `ConcurrencyLimitExceeded` 异常, scorer catch 后写 block reason

### 前端模式

1. **Promise.allSettled + per-source _error 字段** (F15 建立, F16 复用):
   ```ts
   const [aRes, bRes] = await Promise.allSettled([...]);
   const a = aRes.status === 'fulfilled' ? aRes.value.data : [];
   const a_error = aRes.status === 'rejected'
     ? String((aRes.reason as any)?.message ?? aRes.reason ?? 'unknown')
     : undefined;
   ```

2. **后端聚合 > 前端聚合** (F20):
   - 传输 <1 KB 摘要, SQL LIMIT 精准, 客户端 CPU 释放

3. **受控 draft + onBlur commit** (F18):
   - `useState<string>('')` draft + useEffect sync from settings + onBlur 校验后 patch.mutate

4. **WS reconnect invalidate** (F21):
   - `ws.onopen` 前 detect `attemptRef > 0` (wasReconnect) → invalidate keys

### SDD 流程模式

- **每 batch = spec + plan + fix**, 分 3 commits (trivial 时 spec+plan 合并 1 commit + fix 1 commit)
- **subagent-driven implementer + 独立 reviewer** (haiku for trivial, sonnet for judgment)
- **RED → GREEN → regression → sanity → single commit**, 每批 20-60 min
- **越小的 change 越 inline** (F19 / F21 / SR cleanup 直接 Edit, 不 dispatch subagent)

---

## 四、测试状态

### 修完当前 test suite

```
485 passed, 4 pre-existing failed
```

**4 未修 failures (非 audit scope)**:
- `test_deepseek_adapter.py` 3 tests (AI adapter 依赖不同 mock)
- `test_v5_scoring_pipeline.py::test_shadow_ai_infra_error_passes_through_and_opens_paper_trade` (SHADOW AI 兜底路径)

这些**与 audit 21 findings 无关**,是 pre-existing debt, 建议未来独立 batch 处理。

### 前端 hook tests

```
13/13 pass across 5 files
```

- useV5Signals (2), useV5WebSocket (3), useV5ManualOrder (2)
- useV5ActivePositions (3, Batch 15)
- useV5Dashboard (3, Batch 16 → Batch 20 重写)

---

## 五、文档留档

**Specs** (`docs/superpowers/specs/`):
- `2026-07-04-bug-fix-batch-{1-16}-F*-design.md`
- `2026-07-04-bug-fix-batch-{17-21}-F*-design.md`

**Plans** (`docs/superpowers/plans/`):
- `2026-07-04-bug-fix-batch-{1-21}-F*.md`

**Ledger**: `.superpowers/sdd/progress.md`

**Memory files** (`~/.claude/projects/.../memory/`):
- 每 batch 一份 memory (batch-1 到 batch-16 独立),Batches 17-21 合并 1 份
- MEMORY.md 索引更新

---

## 六、后续候选

### 已识别但未修 (不在本次 scope)

1. **4 pre-existing test failures** (deepseek + scoring_pipeline)
2. **BacktestPage 用户手动切换报告 overwrite** — F19 audit 描述的深层问题, 需引入"已手动选择过" flag
3. **`_update_closed` fetch_my_trades 回填 PERMANENT 场景真实价** — F14 audit 建议但 YAGNI 未做
4. **paper_trades / positions_v5 id 冲突处理** — F12 声明的已知失效模式, 生产极小概率
5. **LIVE 路径的 open_position 并发校验** — F11 只做 paper 侧, LIVE 后续 batch

### 建议

- CI 应加 `test_deepseek_adapter.py` + `test_v5_scoring_pipeline.py` 修 debt 的 batch
- 若未来做多 scorer 实例, 优先处理 F11 LIVE 侧
- Dashboard 消费者(DashboardPage / OverviewPage / PortfolioPage 等) 后续加降级 UI 提示时消费 F15/F16/F20 提供的 `errors` 字段

---

## 七、Metrics

- **总提交数**: 43 commits (含 spec/plan/impl/test)
- **总代码 diff**: ~9000 行 (含 spec/plan docs)
- **执行时长**: 一个会话内完成 21 batches + SR cleanup
- **subagent dispatch**: 21 implementer + 15 task reviewer + 0 final review
- **failed batches**: 0 (每批 RED → GREEN 成功首次)

---

*Generated 2026-07-04 by audit closure session. See `docs/audit-2026-07/bug-fix-list.md` for original findings.*
