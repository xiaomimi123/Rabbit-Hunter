# Tech Debt · 2026-07

> 生成日期: 2026-07-03
> 只列观察，不含修复动作。修复由后续 spec 决定。
> 每条 finding 用 CONFIRMED / PLAUSIBLE 标注置信度。
> CONFIRMED = 能命名触发 input/state，且效果可观测。
> PLAUSIBLE = 代码形状可疑，但无法确定触发路径或后果被防御代码部分覆盖。

---

## Findings 汇总

| # | 标题 | 位置 | 置信度 |
|---|---|---|---|
| 1 | `LOCAL_DB_PATH` vs `DB_PATH` 命名分裂 | `api/routes/v5_walkforward.py:33` | CONFIRMED |
| 2 | `SL_TP_FAIL_OPEN` 模块常量不随 Settings UI 变化 | `scripts/v5_position_manager.py:20`, `scripts/okx_trader.py:36` | CONFIRMED |
| 3 | `close_position` 吞掉 broker 失败后仍标 CLOSED | `scripts/v5_position_manager.py:226-248` | CONFIRMED |
| 4 | `preview` 端点从 0 行 `ai_training_data` 读胜率 | `api/routes/v5_strategy_config.py:136-149` | CONFIRMED |
| 5 | `get_param()` 吞掉 DB 查询错误，无日志 | `scripts/v5_params.py:85` | CONFIRMED |
| 6 | walkforward daemon 线程在 API 重启后状态卡死 | `api/routes/v5_walkforward.py:284-288` | CONFIRMED |
| 7 | `_resolve_leverage()` 裸 `except Exception: pass` | `scripts/paper_position_manager.py:87` | PLAUSIBLE |
| 8 | `V5Scorer.run()` 外层异常兜底静默丢弃 enriched item | `scripts/tasks/scorer.py:464` | PLAUSIBLE |
| 9 | max_concurrent 检查与 open_position 不原子 | `scripts/tasks/scorer.py:228` | PLAUSIBLE |
| 10 | LIVE 模式余额拉取失败时以 paper 余额代入风险计算 | `scripts/tasks/collector_main.py:68-89` | PLAUSIBLE |

---

## Finding 1: `LOCAL_DB_PATH` vs `DB_PATH` 命名分裂

- **位置**: `api/routes/v5_walkforward.py:33`
- **置信度**: CONFIRMED
- **描述**: 所有其他 15+ 个 API 路由文件均通过 `os.environ.get("DB_PATH", "data/rabbit_hunter.db")` 定位数据库，但 `api/routes/v5_walkforward.py:33` 单独使用 `LOCAL_DB_PATH`。`wf_jobs` 表写入目标与其余路由读取目标可能不同。
- **Failure scenario**: 操作员设置 `DB_PATH=data/custom.db` 后重启 API 服务。`POST /api/v5/walkforward/run` 将 job 记录写入 `data/rabbit_hunter.db`（因为 `LOCAL_DB_PATH` 未设置）；`GET /api/v5/signals`、`GET /api/v5/positions` 等全部读 `data/custom.db`。`GET /api/v5/walkforward/jobs/{job_id}` 也读 `data/rabbit_hunter.db`，故 job 状态看起来可用，但所有其他数据来自另一个库，形成逻辑断层。
- **相关代码**:
  ```python
  # api/routes/v5_walkforward.py:33
  return os.environ.get("LOCAL_DB_PATH", "data/rabbit_hunter.db")
  # 对比所有其他路由:
  # return os.environ.get("DB_PATH", "data/rabbit_hunter.db")
  ```

---

## Finding 2: `SL_TP_FAIL_OPEN` 模块常量不随 Settings UI 变化

- **位置**: `scripts/v5_position_manager.py:20`, `scripts/okx_trader.py:36`
- **置信度**: CONFIRMED
- **描述**: `SL_TP_FAIL_OPEN`（v5_position_manager）和 `_SL_TP_FAIL_OPEN`（okx_trader）均在模块加载时从 `os.environ` 读取一次并绑定为模块级常量。Settings 页 `PATCH /api/v5/settings` 将 `sl_tp_fail_open=true` 写入 `system_settings` 表，但 collector 进程已加载完毕，该写入对运行中的状态机无效。
- **Failure scenario**: 操作员在 Settings 页将 `sl_tp_fail_open` 切换为 `true`（意图开启 fail-open 以保留主仓），DB 写入成功，UI 展示 `true`。但 `V5PositionManager.open_position()` 中 `if not SL_TP_FAIL_OPEN` 仍读取进程启动时的 `False`，SL 失败时仍执行 fail-closed 回滚，与操作员预期相反。
- **相关代码**:
  ```python
  # scripts/v5_position_manager.py:20 — 绑定一次，进程生命周期内不变
  SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")

  # scripts/okx_trader.py:36 — 同一模式
  _SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true", "yes")
  ```

---

## Finding 3: `close_position` 吞掉 broker 失败后仍将 DB 标记为 CLOSED

- **位置**: `scripts/v5_position_manager.py:226-248`
- **置信度**: CONFIRMED
- **描述**: `V5PositionManager.close_position()` 在第 226-229 行调用 `self.broker.close_position(symbol)` 并捕获所有异常，仅打印日志后继续执行。后续第 241-248 行的 `conn.execute("UPDATE positions_v5 SET status='CLOSED' ...")` 无论 broker 调用是否成功均会运行。
- **Failure scenario**: LIVE 模式下，网络闪断导致 `broker.close_position(symbol)` 抛出 `RequestTimeout`。异常被打印后代码继续，`positions_v5` 中该行更新为 `status='CLOSED'`。`V5PositionMonitor` 不再轮询该 id（因为 `get_open_positions()` 过滤 `status IN ('OPEN','OPEN_DEGRADED')`），但交易所实际仍持有该仓位，SL/TP 保护单也仍在交易所上挂单，产生孤立交易所持仓，直到手工 reconcile。
- **相关代码**:
  ```python
  # scripts/v5_position_manager.py:226-229
  try:
      self.broker.close_position(symbol)
  except Exception as e:
      print(f"[V5PositionManager] 平仓 broker 失败: {e}")
  # 无 return/re-raise，继续执行 DB UPDATE：
  conn.execute("UPDATE positions_v5 SET status='CLOSED' ... WHERE id=?", ...)
  ```

---

## Finding 4: `preview` 端点从 0 行 `ai_training_data` 读胜率，返回恒为 0.0 的误导性指标

- **位置**: `api/routes/v5_strategy_config.py:136-149`
- **置信度**: CONFIRMED
- **描述**: `POST /api/v5/strategy-config/preview` 在计算 `estimated_win_rate` 时查询 `ai_training_data` 表的 `outcome` 和 `entry_rsi_15m` 字段（第 136-149 行）。`ai_training_data` 本地 SQLite 表当前永久为 0 行（已由 `dead-code-and-tables.md` 核实）。`totals` 始终为 0，`win_rate` 始终为 `0.0`，端点返回 HTTP 200 而非错误，响应内容具有正常 JSON 结构。
- **Failure scenario**: 操作员在 StrategyConfig 页调整 RSI 超买阈值并点击"预览效果"。响应始终显示 `estimated_win_rate: 0.0`，无论阈值如何变化，操作员无法通过该指标区分参数优劣，但不会收到任何错误提示，可能误以为当前阈值无历史胜率。
- **相关代码**:
  ```python
  # api/routes/v5_strategy_config.py:136-150
  wins = conn.execute(
      "SELECT COUNT(*) FROM ai_training_data "
      "WHERE outcome='WIN' AND ..."
      (overbought, oversold),
  ).fetchone()[0] or 0
  totals = conn.execute(...).fetchone()[0] or 0
  win_rate = (wins / totals) if totals else 0.0  # totals 恒为 0
  ```

---

## Finding 5: `get_param()` 吞掉 DB 查询错误，无任何日志

- **位置**: `scripts/v5_params.py:85`
- **置信度**: CONFIRMED
- **描述**: `get_param()` 第 67-85 行的 DB 查询块用 `except Exception: pass` 收尾，不打印任何信息。系统参数（RSI 阈值、SL/TP 乘数、max_concurrent 等）全部通过 `get_param()` 读取。DB 读取失败时所有这些参数静默回退到 `DEFAULTS` 硬编码值。
- **Failure scenario**: DB 文件被锁定（例如另一进程对同一 SQLite 执行备份导致写锁）。`get_param("v5_max_concurrent", 3, int)` 返回 3（默认值），`get_param("v5_rsi_overbought", 70.0, float)` 返回 70.0（默认值）。操作员在 StrategyConfig 页配置的非默认参数（如 `v5_max_concurrent=1`）被静默忽略。日志中无任何警告；唯一的观测手段是对比 trade_scores_v5 中的实际行为与配置页的展示。
- **相关代码**:
  ```python
  # scripts/v5_params.py:85
  except Exception:
      pass
  # 4. default
  return default
  ```

---

## Finding 6: walkforward daemon 线程在 API 进程重启后 job 状态永久卡在 `running`

- **位置**: `api/routes/v5_walkforward.py:284-288`
- **置信度**: CONFIRMED
- **描述**: `POST /api/v5/walkforward/run` 通过 `threading.Thread(..., daemon=True).start()` 在后台线程中运行 `_run_wf_subprocess`。Python daemon 线程在主进程退出时被强制终止，不执行任何清理。`_run_wf_subprocess` 仅在 subprocess 完成或失败后才更新 `wf_jobs.status`。
- **Failure scenario**: 操作员触发一个耗时 5 分钟的 walk-forward 任务，2 分钟后执行 `docker restart` 或 API 进程崩溃。daemon 线程被杀，子进程被孤立（或随 daemon 线程终止）。`wf_jobs` 行的 `status` 停留在 `'running'`，`finished_at` 为 NULL。重启后 `GET /api/v5/walkforward/jobs/{job_id}` 返回 `status='running'`，无超时或失效机制，该状态永久保留，操作员无法区分"仍在运行"与"进程已消失"。
- **相关代码**:
  ```python
  # api/routes/v5_walkforward.py:284-288
  threading.Thread(
      target=_run_wf_subprocess,
      args=(job_id, req.dict()),
      daemon=True,
  ).start()
  ```

---

## Finding 7: `_resolve_leverage()` 裸 `except Exception: pass` 静默丢弃所有错误

- **位置**: `scripts/paper_position_manager.py:87`
- **置信度**: PLAUSIBLE
- **描述**: `PaperPositionManager._resolve_leverage()` 在 `try` 块（第 77-86 行）调用 `get_exchange_config_manager()` 和 `mgr.get_config()`。第 87 行 `except Exception: pass` 捕获所有异常且不记录。函数继续落入 env 变量检查。如果 exchange config 模块本身有 bug（AttributeError、ImportError、DB OperationalError），该错误被完全掩盖。
- **Failure scenario**: `exchange_config_manager.get_exchange_config_manager()` 在数据库迁移期间抛出 `sqlite3.OperationalError`（表不存在）。异常被吞掉，函数读取 `os.environ.get("OKX_LEVERAGE")` 或最终返回默认值 10。若实际配置是 `leverage=3`（轻仓），paper trade 将以 10× 杠杆计算 size，虚拟仓位比预期大 3.3×，KPI 统计失真。
- **相关代码**:
  ```python
  # scripts/paper_position_manager.py:77-88
  try:
      mgr = get_exchange_config_manager(self.supabase)
      active = mgr.get_active_exchange()
      cfg = mgr.get_config(active) or {}
      lev = cfg.get("leverage")
      if lev:
          return int(lev)
  except Exception:
      pass  # 无日志
  ```

---

## Finding 8: `V5Scorer.run()` 外层异常兜底静默丢弃 enriched item

- **位置**: `scripts/tasks/scorer.py:464`
- **置信度**: PLAUSIBLE
- **描述**: `V5Scorer.run()` 第 456-464 行的 `except Exception as e` 捕获 `process_enriched_v5` 及其所有调用链（包括 `_write_trade_score`、`_count_open_positions`）的未预期异常，仅打印一行日志后继续下一个 item。该 item 不重试，`trade_scores_v5` 中不写任何失败记录，健康监控无法检测到该丢失。
- **Failure scenario**: SQLite 在高写入负载下返回 `database is locked`，导致 `_write_trade_score`（`scripts/tasks/scorer.py:141`）内 `conn.execute(...)` 抛出 `OperationalError`。该异常未在 `process_enriched_v5` 内被捕获，冒泡到第 464 行，打印 `[V5Scorer] XYZUSDT 处理异常`。该 enriched item 的全部中间状态（已通过规则层、已请求 AI）丢失，无记录。`_healthcheck_loop` 的"5 分钟无写入"告警在高频场景下可能延迟触发。
- **相关代码**:
  ```python
  # scripts/tasks/scorer.py:456-465
  try:
      mode = self.resolve_mode()
      balance = self.fetch_balance()
      await process_enriched_v5(
          enriched=enriched, ai=self.ai, ...
      )
  except Exception as e:
      print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
  ```

---

## Finding 9: max_concurrent 检查与 `open_position` 调用不在同一原子操作内

- **位置**: `scripts/tasks/scorer.py:228`
- **置信度**: PLAUSIBLE
- **描述**: `process_enriched_v5` 在第 228 行调用 `_count_open_positions(db_path)` 检查当前持仓数，通过后在第 313 行执行 `await ai.decide()`（IO 等待，让出事件循环），最后在第 395-406 行调用 `paper_pm.open_position()` 或 `live_pm.open_position()`。SQLite 层没有跨越 `await` 的事务锁，`_count_open_positions` 结果在 `await` 期间可能已经失效。
- **Failure scenario**: 当前单 scorer 实例串行处理，正常情况下不存在真正并发。但若未来增加多 scorer 实例（或多进程 scorer），两个实例在 `await ai.decide()` 前均读到 count=2（上限 3），均通过检查，均完成 AI 调用后各自插入持仓，最终 count=4，超过 `_max_concurrent()`。
- **相关代码**:
  ```python
  # scripts/tasks/scorer.py:228
  if _count_open_positions(db_path) >= _max_concurrent():
      # ...
      return
  # ...
  ai_result = await ai.decide(enriched, indicators, decision, risk)  # 让出事件循环
  # 此后无二次检查直接开仓
  position_id = paper_pm.open_position(...)
  ```

---

## Finding 10: LIVE 模式余额拉取失败时以 paper 余额代入全链路风险计算

- **位置**: `scripts/tasks/collector_main.py:68-89`
- **置信度**: PLAUSIBLE
- **描述**: `_fetch_balance()` 在 LIVE 模式下若 broker `fetch_balance()` 调用失败（网络、鉴权、格式解析），在第 88-89 行打印日志后返回 `_PAPER_BALANCE`（默认 1000 USDT）。该值随后流入 `_risk_per_trade(balance_usdt)` → `plan()` → `gate_per_trade_risk(equity_usdt=...)` 等整个风险计算链。
- **Failure scenario**: LIVE 账户实际余额 200 USDT，broker 因 API 限速返回 429，`_fetch_balance()` 回退到 1000 USDT。`_risk_per_trade(1000)` 返回 1%，`plan()` 计算 `size_usdt = 1000 × 0.01 / sl_dist_pct / leverage`，得出的 size 是实际承受能力的 5×。`gate_per_trade_risk` 也以 1000 为分母，无法拦截。订单以 200 USDT 账户本金承受 1000 USDT 等价风险敞口提交到交易所。
- **相关代码**:
  ```python
  # scripts/tasks/collector_main.py:85-89
  except Exception as e:
      print(f"[collector_main] LIVE 余额拉取失败,用 PAPER_INITIAL_BALANCE_USDT: {e}")
  return _PAPER_BALANCE  # 默认 1000 USDT，无论 LIVE 账户真实余额多少
  ```

---

*本文件为只读观察，不含修复动作。修复方案见后续 spec 文档。*
*交叉参考：`dead-code-and-tables.md` 覆盖无调用路径的模块和 0 行表；本文件仅列有调用路径但存在隐患的代码。*
