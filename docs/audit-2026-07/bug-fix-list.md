# Bug 修复清单 — Rabbit-Hunter 2026-07

> 生成日期: 2026-07-03
> 审计方式: Solo sonnet — 后端深读 9 文件 + 中读 ~15 API 路由 + 前端深读 5 页
> 前置文件: `docs/audit-2026-07/tech-debt.md`（Phase 0，10 条 observation-only findings）
> Phase 0 原始描述和 Failure scenario 保留，本文仅补 Fix 建议 + 优先级 + 测试建议

---

## 一、执行摘要

### Phase 0 十条落位

| Phase 0 编号 | 原标题 | 本次编号 | 优先级 |
|---|---|---|---|
| 1 | LOCAL_DB_PATH vs DB_PATH 命名分裂 | Finding 6 | P1 |
| 2 | SL_TP_FAIL_OPEN 模块常量不随 Settings UI 变化 | Finding 1 | P0 |
| 3 | close_position 吞掉 broker 失败后仍标 CLOSED | Finding 2 | P0 |
| 4 | preview 端点从 0 行 ai_training_data 读胜率 | Finding 7 | P1 |
| 5 | get_param() 吞掉 DB 查询错误，无日志 | Finding 8 | P1 |
| 6 | walkforward daemon 线程在 API 重启后状态卡死 | Finding 9 | P1 |
| 7 | _resolve_leverage() 裸 except Exception: pass | Finding 17 | P2 |
| 8 | V5Scorer.run() 外层异常兜底静默丢弃 enriched item | Finding 10 | P1 |
| 9 | max_concurrent 检查与 open_position 不原子 | Finding 11 | P1 |
| 10 | LIVE 模式余额拉取失败时以 paper 余额代入风险计算 | Finding 3 | P0 |

### 本次新增

本次扫描新增 11 条（后端 5 / 前端 6）。

### 合计

- **P0**: 5 条（Finding 1、2、3、4、5）
- **P1**: 11 条（Finding 6-16）
- **P2**: 5 条（Finding 17-21）
- **总计**: 21 条（后端 15 / 前端 6）

### 建议修复顺序

1. **P0 全修**（Finding 1-5）：任何一条在 LIVE 模式下均可导致真实资金损失或仓位永久孤立
2. **P1 前 5 修**（Finding 6、7、8、12、15）：数据一致性问题，影响风控可见性

---

## 二、P0 Findings（真钱风险）

---

## Finding 1: SL_TP_FAIL_OPEN 模块常量不随 Settings UI 变化

- **位置**: `scripts/v5_position_manager.py:20`, `scripts/okx_trader.py:36`
- **置信度**: CONFIRMED
- **优先级**: P0
- **描述**: `SL_TP_FAIL_OPEN`（v5_position_manager）和 `_SL_TP_FAIL_OPEN`（okx_trader）均在模块加载时从 `os.environ` 读取一次并绑定为模块级常量。Settings 页 `PATCH /api/v5/settings` 将 `sl_tp_fail_open=true` 写入 `system_settings` 表，但 collector 进程已加载完毕，该写入对运行中的状态机无效。
- **Failure scenario**: 操作员在 Settings 页将 `sl_tp_fail_open` 切换为 `true`（意图开启 fail-open 以保留主仓），DB 写入成功，UI 展示 `true`。但 `V5PositionManager.open_position()` 中 `if not SL_TP_FAIL_OPEN` 仍读取进程启动时的 `False`，SL 失败时仍执行 fail-closed 回滚，与操作员预期相反。反向场景同样危险：进程以 `SL_TP_FAIL_OPEN=true` 启动，操作员想切回 fail-closed，UI 改成功但运行时不生效，SL 失败时主仓被错误保留。
- **Fix 建议**: 将两处模块级常量改为每次调用时从 DB 实时读取。参考 scorer.py 已有的 `_ai_fail_open(db_path)` 和 `_enable_auto_trading(db_path)` 范式——直接 `sqlite3.connect(db_path).execute("SELECT value FROM system_settings WHERE key='sl_tp_fail_open' ...")` 并在 `open_position` 入口读取。`open_position` 调用频率不高（每次开仓调一次），额外 DB 查询代价可忽略。
- **测试建议**: 集成测试：进程加载时设 env `SL_TP_FAIL_OPEN=false`，之后向 DB 写入 `sl_tp_fail_open=true`，触发模拟 SL 挂单失败，断言主仓被保留（fail-open 生效）。同样测试反向切换。

---

## Finding 2: close_position 吞掉 broker 失败后仍将 DB 标记为 CLOSED

- **位置**: `scripts/v5_position_manager.py:226-248`
- **置信度**: CONFIRMED
- **优先级**: P0
- **描述**: `V5PositionManager.close_position()` 在第 226-229 行调用 `self.broker.close_position(symbol)` 并捕获所有异常，仅打印日志后继续执行。后续第 241-248 行的 `conn.execute("UPDATE positions_v5 SET status='CLOSED' ...")` 无论 broker 调用是否成功均会运行。
- **Failure scenario**: LIVE 模式下，网络闪断导致 `broker.close_position(symbol)` 抛出 `RequestTimeout`。异常被打印后代码继续，`positions_v5` 中该行更新为 `status='CLOSED'`。`V5PositionMonitor` 不再轮询该 id（因为 `get_open_positions()` 过滤 `status IN ('OPEN','OPEN_DEGRADED')`），但交易所实际仍持有该仓位，SL/TP 保护单也仍在交易所上挂单，产生孤立交易所持仓，直到手工 reconcile。
- **Fix 建议**: 将 `broker.close_position` 失败分两条路处理：(a) 可重试的瞬时错误（NetworkError/RequestTimeout）— 抛出异常，让调用方（V5PositionMonitor）决定是否重试，不更新 DB；(b) 永久失败 — 把 DB 状态改为 `'ERROR_RECONCILE_NEEDED'`（与 `open_position` 中已有的错误路径对齐），记录 `error_context` JSON，而不是 `'CLOSED'`。伪代码：
  ```python
  try:
      self.broker.close_position(symbol)
  except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
      raise  # 让上层重试
  except Exception as e:
      error_ctx = json.dumps({"close_error": str(e)})
      conn.execute("UPDATE positions_v5 SET status='ERROR_RECONCILE_NEEDED', error_context=? WHERE id=?", (error_ctx, position_id))
      conn.commit()
      return
  # 只有 broker 成功后才写 CLOSED
  conn.execute("UPDATE positions_v5 SET status='CLOSED' ...")
  ```
- **测试建议**: 单测：mock `broker.close_position` 抛 `ccxt.RequestTimeout`，调用 `close_position()`，断言 positions_v5 行为 `ERROR_RECONCILE_NEEDED` 而非 `CLOSED`。

---

## Finding 3: LIVE 模式余额拉取失败时以 paper 余额代入全链路风险计算

- **位置**: `scripts/tasks/collector_main.py:68-89`
- **置信度**: PLAUSIBLE
- **优先级**: P0
- **描述**: `_fetch_balance()` 在 LIVE 模式下若 broker `fetch_balance()` 调用失败（网络、鉴权、格式解析），在第 88-89 行打印日志后返回 `_PAPER_BALANCE`（默认 1000 USDT）。该值随后流入 `_risk_per_trade(balance_usdt)` → `plan()` → `gate_per_trade_risk(equity_usdt=...)` 等整个风险计算链。
- **Failure scenario**: LIVE 账户实际余额 200 USDT，broker 因 API 限速返回 429，`_fetch_balance()` 回退到 1000 USDT。`_risk_per_trade(1000)` 返回 1%，`plan()` 计算 `size_usdt = 1000 × 0.01 / sl_dist_pct / leverage`，得出的 size 是实际承受能力的 5×。`gate_per_trade_risk` 也以 1000 为分母，无法拦截。订单以 200 USDT 账户本金承受 1000 USDT 等价风险敞口提交到交易所。
- **Fix 建议**: LIVE 模式余额拉取失败时，不应回退到 `_PAPER_BALANCE`，而应停止开仓（返回 sentinel 值或抛异常）。改法：在 except 块不再 return `_PAPER_BALANCE`，而是 `return None`；在调用方 `V5Scorer.run()` 中若 `balance is None` 则写 `block_reason="BALANCE_UNAVAILABLE"` 并跳过该 item。
  ```python
  except Exception as e:
      print(f"[collector_main] LIVE 余额拉取失败,跳过本次开仓: {e}")
      return None  # 调用方检查 None 并 block
  ```
- **测试建议**: 集成测试：mock broker `fetch_balance` 抛 `RequestTimeout`，切 LIVE 模式，断言 scorer 写入 `block_reason='BALANCE_UNAVAILABLE'` 而非实际开仓。

---

## Finding 4: V5PositionManager 调用 self.broker.create_order() — 方法在 OkxTrader/BinanceTrader 上不存在

- **位置**: `scripts/v5_position_manager.py:80`, `scripts/v5_position_manager.py:94`, `scripts/v5_position_manager.py:135`
- **置信度**: CONFIRMED
- **优先级**: P0
- **描述**: `V5PositionManager.open_position()` 的三个阶段（主仓、SL 挂单、TP 挂单）均调用 `self.broker.create_order(...)`。但 broker 实例是 `OkxTrader` 或 `BinanceTrader`（由 `get_trader()` 返回），两个类均不暴露 `create_order` 实例方法（只有 `self.exchange.create_order` 属于内层 ccxt 对象，不属于 trader wrapper）。每次 LIVE 开仓尝试在阶段 1 均触发 `AttributeError`，被 `except Exception` 包装后以 "主仓下单失败: AttributeError" 上抛，scorer 写 `OPEN_FAILED`，无任何真实 LIVE 仓位能被打开。
- **Failure scenario**: 启用 LIVE 模式后，任何策略信号均触发 `live_pm.open_position(...)`，内部调用 `self.broker.create_order(...)`，立即抛 `AttributeError: 'OkxTrader' object has no attribute 'create_order'`。所有 LIVE 开仓静默失败（仅 `trade_scores_v5.block_reason = 'OPEN_FAILED:AttributeError'`），操作员看到系统在跑但无 LIVE 实仓，直到手动排查日志才能发现。
- **Fix 建议**: 三处 `self.broker.create_order(...)` 调用需替换为 broker 实际暴露的接口。具体：
  - **阶段 1（主仓）**: 调 `self.broker.open_position(symbol=symbol, side=side, quantity=position_size_coins)` 并检查返回 `result.get("success")`
  - **阶段 2（SL）**: 调 `self.broker.set_stop_loss(symbol=symbol, stop_price=sl_price, side=side)` 并检查结果
  - **阶段 3（TP）**: 调 `self.broker.set_take_profit(symbol=symbol, take_profit_price=tp_price, side=side)`
  同时需要处理返回 dict（而非抛异常）的 OkxTrader/BinanceTrader 失败路径，按 `result.get("success")` 决定 fail-closed/fail-open 分支。
- **测试建议**: 单测：用 mock broker（spy `set_stop_loss`/`set_take_profit`/`open_position`），调用 `V5PositionManager.open_position()`，断言不再调用 `create_order`，且正确调用了三个接口方法。LIVE 冒烟测试：在测试网开一个真实仓位，确认 `positions_v5` 有 `status='OPEN'` 记录。

---

## Finding 5: V5PositionMonitor 在 LIVE 模式 live_pm 为 None 时静默停止监控所有持仓

- **位置**: `scripts/v5_position_monitor.py:184-187`
- **置信度**: CONFIRMED
- **优先级**: P0
- **描述**: `V5PositionMonitor._tick()` 第 185-187 行：当 `mode == "LIVE"` 时 `pm = self.live_pm`，若 `live_pm` 为 None（trader 初始化失败时 `collector_main.py` 置 None），则 `if not pm: return` 立即退出，不做任何监控。每 30s 的 tick 均无操作，所有 LIVE 仓位的 SL/TP 触发检查、软时限平仓、信号反转平仓均不执行。
- **Failure scenario**: OKX API 密钥在 collector 启动时因网络超时初始化失败，`live_pm = None`。系统模式切换至 LIVE 并开仓（若使用另一路径）。Monitor 每 30s 进 _tick 后立即返回，不检查任何仓位。仓位到达软时限后不平仓；行情反转后 RSI/MACD 触发 SIGNAL_REVERSE 不执行；SL 被触发但已 DB 无 paper_pm 路径，LIVE 仓位在交易所自动成交 SL 但 DB 仍为 OPEN，持仓状态永久不一致。
- **Fix 建议**: 不应静默 return，而应：
  1. 日志 WARN 输出当前 LIVE 模式但 `live_pm` 为 None 的异常状态
  2. 尝试重新初始化 trader（`_get_live_trader()`），成功则更新 `self.live_pm`
  3. 若仍失败，至少输出错误并将 monitor 状态暴露给 healthcheck（写一个 `ws_event_queue` 事件通知前端）
  伪代码：
  ```python
  if not pm:
      print("[V5PositionMonitor] WARN: LIVE 模式但 live_pm 为 None,尝试重新初始化 trader")
      try:
          from scripts.exchange_factory import get_trader
          from scripts.v5_position_manager import V5PositionManager
          trader = get_trader()
          if trader:
              self.live_pm = V5PositionManager(broker=trader, db_path=self.db_path)
              pm = self.live_pm
      except Exception as e:
          print(f"[V5PositionMonitor] trader 重新初始化失败: {e}")
          return
  ```
- **测试建议**: 集成测试：以 `live_pm=None` 构造 V5PositionMonitor，调 `_tick()`，断言打印 WARN 日志；mock `get_trader()` 成功，断言第二次 tick 时 `live_pm` 已更新且能处理仓位。

---

## 三、P1 Findings（数据 / 状态一致性）

---

## Finding 6: LOCAL_DB_PATH vs DB_PATH 命名分裂

- **位置**: `api/routes/v5_walkforward.py:33`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: 所有其他 15+ 个 API 路由文件均通过 `os.environ.get("DB_PATH", "data/rabbit_hunter.db")` 定位数据库，但 `api/routes/v5_walkforward.py:33` 单独使用 `LOCAL_DB_PATH`。`wf_jobs` 表写入目标与其余路由读取目标可能不同。
- **Failure scenario**: 操作员设置 `DB_PATH=data/custom.db` 后重启 API 服务。`POST /api/v5/walkforward/run` 将 job 记录写入 `data/rabbit_hunter.db`（因为 `LOCAL_DB_PATH` 未设置）；`GET /api/v5/signals`、`GET /api/v5/positions` 等全部读 `data/custom.db`。`GET /api/v5/walkforward/jobs/{job_id}` 也读 `data/rabbit_hunter.db`，故 job 状态看起来可用，但所有其他数据来自另一个库，形成逻辑断层。
- **Fix 建议**: 将 `api/routes/v5_walkforward.py` 中 `_db_path()` 函数改为与其他路由一致，读取 `DB_PATH` 环境变量：
  ```python
  def _db_path() -> str:
      return os.environ.get("DB_PATH", "data/rabbit_hunter.db")
  ```
  同时检索是否有任何系统文档或部署说明中将 `LOCAL_DB_PATH` 写死，若有则同步更新。
- **测试建议**: 集成测试：设 `DB_PATH=data/test.db`，调用 `POST /api/v5/walkforward/run`，断言 `data/test.db` 中 `wf_jobs` 表有该 job 记录，而非 `data/rabbit_hunter.db`。

---

## Finding 7: preview 端点从 0 行 ai_training_data 读胜率，返回恒为 0.0 的误导性指标

- **位置**: `api/routes/v5_strategy_config.py:136-149`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `POST /api/v5/strategy-config/preview` 在计算 `estimated_win_rate` 时查询 `ai_training_data` 表的 `outcome` 和 `entry_rsi_15m` 字段（第 136-149 行）。`ai_training_data` 本地 SQLite 表当前永久为 0 行（已由 `dead-code-and-tables.md` 核实）。`totals` 始终为 0，`win_rate` 始终为 `0.0`，端点返回 HTTP 200 而非错误，响应内容具有正常 JSON 结构。
- **Failure scenario**: 操作员在 StrategyConfig 页调整 RSI 超买阈值并点击"预览效果"。响应始终显示 `estimated_win_rate: 0.0`，无论阈值如何变化，操作员无法通过该指标区分参数优劣，但不会收到任何错误提示，可能误以为当前阈值无历史胜率。
- **Fix 建议**: 将查询来源改为 `paper_trades`（已有真实历史数据）。用 `entry_rsi_15m` 字段过滤，计算符合 RSI 阈值范围内的纸面交易胜率。若 `paper_trades.entry_rsi_15m` 为空则使用 `trade_scores_v5` 的 `rsi_15m`/`should_trade`/`executed` 字段做代理统计。同时在响应中加 `data_source` 字段（`"paper_trades"` 或 `"no_data"`）和 `sample_n`，让前端能区分"真实历史"与"零数据"。
- **测试建议**: 单测：插入若干 `paper_trades` 含 `entry_rsi_15m` 和 `exit_reason` 列，调用 `preview(overbought=70, oversold=30)`，断言 `estimated_win_rate` 不为 0.0 且与手算一致。

---

## Finding 8: get_param() 吞掉 DB 查询错误，无任何日志

- **位置**: `scripts/v5_params.py:85`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `get_param()` 第 67-85 行的 DB 查询块用 `except Exception: pass` 收尾，不打印任何信息。系统参数（RSI 阈值、SL/TP 乘数、max_concurrent 等）全部通过 `get_param()` 读取。DB 读取失败时所有这些参数静默回退到 `DEFAULTS` 硬编码值。
- **Failure scenario**: DB 文件被锁定（例如另一进程对同一 SQLite 执行备份导致写锁）。`get_param("v5_max_concurrent", 3, int)` 返回 3（默认值），`get_param("v5_rsi_overbought", 70.0, float)` 返回 70.0（默认值）。操作员在 StrategyConfig 页配置的非默认参数（如 `v5_max_concurrent=1`）被静默忽略。日志中无任何警告；唯一的观测手段是对比 trade_scores_v5 中的实际行为与配置页的展示。
- **Fix 建议**: 将 `except Exception: pass` 改为记录 WARN 日志：
  ```python
  except Exception as e:
      print(f"[get_param] DB 读取失败,使用默认值 {key}={default}: {type(e).__name__}: {e}")
  return default
  ```
  另考虑使用 `logging.warning` 替代 `print`，便于日志聚合系统过滤。
- **测试建议**: 单测：传入不存在的 DB 路径，调 `get_param("any_key", 99, int)`，断言返回 99 且标准错误输出包含 WARN/warning 字符串。

---

## Finding 9: walkforward daemon 线程在 API 进程重启后 job 状态永久卡在 running

- **位置**: `api/routes/v5_walkforward.py:284-288`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `POST /api/v5/walkforward/run` 通过 `threading.Thread(..., daemon=True).start()` 在后台线程中运行 `_run_wf_subprocess`。Python daemon 线程在主进程退出时被强制终止，不执行任何清理。`_run_wf_subprocess` 仅在 subprocess 完成或失败后才更新 `wf_jobs.status`。
- **Failure scenario**: 操作员触发一个耗时 5 分钟的 walk-forward 任务，2 分钟后执行 `docker restart` 或 API 进程崩溃。daemon 线程被杀，子进程被孤立（或随 daemon 线程终止）。`wf_jobs` 行的 `status` 停留在 `'running'`，`finished_at` 为 NULL。重启后 `GET /api/v5/walkforward/jobs/{job_id}` 返回 `status='running'`，无超时或失效机制，该状态永久保留，操作员无法区分"仍在运行"与"进程已消失"。
- **Fix 建议**: API 启动时（模块加载阶段 `_ensure_jobs_table()` 之后），执行"僵尸清理"：将所有 `status='running'` 且 `started_at` 超过阈值（如 2 小时）的 job 改为 `status='failed'`，`error='进程重启时任务中断'`。同时可增加 `started_at` 的超时判断：
  ```python
  def _cleanup_stale_jobs():
      conn = sqlite3.connect(_db_path())
      try:
          conn.execute("""
              UPDATE wf_jobs SET status='failed', finished_at=datetime('now'),
                error='进程重启时任务中断 (stale cleanup)'
              WHERE status IN ('running','queued')
                AND started_at < datetime('now', '-2 hours')
          """)
          conn.commit()
      finally:
          conn.close()
  _cleanup_stale_jobs()
  ```
- **测试建议**: 单测：预插一条 `status='running'`、`started_at=3 hours ago` 的 job，触发模块重载，断言该 job 转为 `failed`。

---

## Finding 10: V5Scorer.run() 外层异常兜底静默丢弃 enriched item

- **位置**: `scripts/tasks/scorer.py:464`
- **置信度**: PLAUSIBLE
- **优先级**: P1
- **描述**: `V5Scorer.run()` 第 456-464 行的 `except Exception as e` 捕获 `process_enriched_v5` 及其所有调用链（包括 `_write_trade_score`、`_count_open_positions`）的未预期异常，仅打印一行日志后继续下一个 item。该 item 不重试，`trade_scores_v5` 中不写任何失败记录，健康监控无法检测到该丢失。
- **Failure scenario**: SQLite 在高写入负载下返回 `database is locked`，导致 `_write_trade_score`（`scripts/tasks/scorer.py:141`）内 `conn.execute(...)` 抛出 `OperationalError`。该异常未在 `process_enriched_v5` 内被捕获，冒泡到第 464 行，打印 `[V5Scorer] XYZUSDT 处理异常`。该 enriched item 的全部中间状态（已通过规则层、已请求 AI）丢失，无记录。`_healthcheck_loop` 的"5 分钟无写入"告警在高频场景下可能延迟触发。
- **Fix 建议**: 在 `except Exception` 块中，在打印日志之后额外写入一条最小失败记录：
  ```python
  except Exception as e:
      print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
      try:
          _write_trade_score(
              db_path, enriched, indicators if 'indicators' in dir() else _dummy_indicators(),
              decision if 'decision' in dir() else _dummy_decision(),
              block_reason=f"INTERNAL_ERROR:{type(e).__name__}",
          )
      except Exception:
          pass  # 写入失败了也不能再抛
  ```
  或更简单：catch 更细粒度的异常，让非 DB 写入的 `OperationalError` 从 `_write_trade_score` 内部被重试而非丢弃。
- **测试建议**: 单测：mock `_write_trade_score` 在第一次调用时抛 `sqlite3.OperationalError("database is locked")`，断言后续调用回退到 `block_reason='INTERNAL_ERROR'` 记录而不是完全丢弃。

---

## Finding 11: max_concurrent 检查与 open_position 调用不在同一原子操作内

- **位置**: `scripts/tasks/scorer.py:228`
- **置信度**: PLAUSIBLE
- **优先级**: P1
- **描述**: `process_enriched_v5` 在第 228 行调用 `_count_open_positions(db_path)` 检查当前持仓数，通过后在第 313 行执行 `await ai.decide()`（IO 等待，让出事件循环），最后在第 395-406 行调用 `paper_pm.open_position()` 或 `live_pm.open_position()`。SQLite 层没有跨越 `await` 的事务锁，`_count_open_positions` 结果在 `await` 期间可能已经失效。
- **Failure scenario**: 当前单 scorer 实例串行处理，正常情况下不存在真正并发。但若未来增加多 scorer 实例（或多进程 scorer），两个实例在 `await ai.decide()` 前均读到 count=2（上限 3），均通过检查，均完成 AI 调用后各自插入持仓，最终 count=4，超过 `_max_concurrent()`。
- **Fix 建议**: 在 `paper_pm.open_position()` 或 `live_pm.open_position()` 内部通过 SQLite 悲观锁（BEGIN IMMEDIATE）在同一事务内做二次 count 检查并插入：
  ```python
  with sqlite3.connect(db_path) as conn:
      conn.execute("BEGIN IMMEDIATE")
      n = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
      if n >= max_concurrent:
          raise ConcurrentLimitExceeded()
      conn.execute("INSERT INTO paper_trades ...")
      conn.commit()
  ```
  短期：至少在 `open_position` 入口再做一次 count 检查（double-check），减少 TOCTOU 窗口。
- **测试建议**: 并发测试：同时发起 4 个 `open_position` 调用（asyncio.gather），断言最终 `paper_trades` 中 OPEN 记录数不超过 `_max_concurrent()` 上限。

---

## Finding 12: v5_position_close 端点只关闭 paper_trades，LIVE 仓位请求返回 404

- **位置**: `api/routes/v5_position_close.py:43`, `api/routes/v5_position_close.py:54`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `POST /api/v5/positions/{position_id}/close` 仅查询 `paper_trades` 表（第 43 行），若 position_id 指向 `positions_v5`（LIVE 仓位），则返回 HTTP 404。PaperPositionManager 只能操作 `paper_trades`，无法关闭 LIVE 仓位。代码注释已承认 "MVP 只支持 paper_trades — LIVE 走 V5PositionManager.close_position 需要 broker 实例，前端 LIVE 单的手动平仓后续单独做"，但实际上前端 `useV5ClosePosition` 对两类仓位均调用该端点。
- **Failure scenario**: LIVE 模式下，操作员在 Dashboard 点击"手动平仓 LIVE 仓位"，前端调用 `POST /api/v5/positions/{live_position_id}/close`。API 查 `paper_trades` 无此 id，返回 HTTP 404。前端显示"平仓失败"，而交易所仍持有该仓位，SL/TP 仍挂单。操作员无法通过 UI 手动干预 LIVE 持仓。
- **Fix 建议**: 在端点中先查 `paper_trades`，不存在则查 `positions_v5`：
  ```python
  # 先试 paper
  row = conn.execute("SELECT status FROM paper_trades WHERE id=?", (position_id,)).fetchone()
  if row is None:
      # 再试 live
      row_live = conn.execute("SELECT status FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
      if row_live is None:
          raise HTTPException(404, ...)
      # 走 V5PositionManager 路径（需要 broker 实例）
      from scripts.exchange_factory import get_trader
      from scripts.v5_position_manager import V5PositionManager
      broker = get_trader()
      live_pm = V5PositionManager(broker=broker, db_path=db)
      live_pm.close_position(position_id, exit_price=body.exit_price, exit_reason=body.exit_reason)
      ...
  ```
- **测试建议**: 集成测试：在 `positions_v5` 插入一条 OPEN LIVE 记录，调用 `POST /api/v5/positions/{id}/close`，断言返回 200 且 `positions_v5` 状态变为 CLOSED。

---

## Finding 13: manual-order execute 端点绕过所有 M3 铁律风控检查

- **位置**: `api/routes/v5_manual_order.py:141-169`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `POST /api/v5/manual-order/execute` 的 `execute()` 函数强制设置 `should_trade=True` 和 `ai.execute=True`，直接调用 `PaperPositionManager.open_position()`，未调用任何 `gate_*` 铁律函数（`gate_final_sl_ratio`、`gate_min_rr`、`gate_sl_attached`、`gate_liquidation_distance`、`gate_per_trade_risk`、`gate_daily_drawdown`）。同时跳过 `_count_open_positions()` max_concurrent 检查和 `_enable_auto_trading()` 检查。
- **Failure scenario**: 操作员在 V5ManualOrderPage 手动开 SHORT 仓，系统当日已亏损 3%（日熔断阈值），但 `gate_daily_drawdown` 未被调用，仓位成功写入 `paper_trades`。RAG 系统后续学习到该笔"已在熔断后开仓"的 paper 交易结果，污染训练数据。同时若 SL 设置违反 SL/ATR 比例铁律，仓位仍被接受，反射工作者录入异常 setup_type 数据。
- **Fix 建议**: 在 execute 函数中复用 `process_enriched_v5` 的铁律检查子集，或至少调用：
  ```python
  from scripts.risk_gates import gate_daily_drawdown, gate_per_trade_risk, gate_min_rr
  from scripts.risk_gates import IronlawViolation, get_today_realized_pnl
  balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
  try:
      gate_daily_drawdown(equity_usdt=balance, today_realized_pnl=get_today_realized_pnl(db))
      gate_min_rr(sl_distance=..., tp_distance=...)
      gate_per_trade_risk(equity_usdt=balance, planned_loss_usdt=..., cap_pct=risk_pct)
  except IronlawViolation as e:
      raise HTTPException(422, detail=f"铁律拒单: {e.kind}")
  ```
- **测试建议**: 单测：在日亏损超 3% 后调用 execute，断言 HTTP 422 而非 200；SL ATR ratio 违规时同样被拒绝。

---

## Finding 14: LIVE 模式 DB exit_price 为 monitor tick 价，非交易所实际成交价

- **位置**: `scripts/v5_position_monitor.py:256`
- **置信度**: PLAUSIBLE
- **优先级**: P1
- **描述**: `V5PositionMonitor._tick()` 通过比对当前拉取的市价与 DB 中 `sl_price`/`tp_price` 判断是否触发退出，触发后以 `market["price"]`（当前 tick 的市价）为 `exit_price` 写入 `positions_v5`。但在 LIVE 模式下，交易所可能已经以实际 SL/TP 触发价（止损单成交价）成交，monitor tick 时的价格可能已偏离成交价数个 bps 至百分比。
- **Failure scenario**: BTC 下跌至 SL 价 60000，交易所触发 stop_market 订单以 59990 成交（滑点）。Monitor 30s 后 tick，当前价已回升至 60050。`check_exit_triggers` 不再判定 SL_HIT（60050 > 60000），但如果已成交则交易所无持仓。若下次 monitor tick 时价格再低于 SL，`broker.close_position(symbol)` 返回"无持仓"，monitor 仍以当时价（如 59800）写入 DB。实际成交价 59990 从未记录，DB 显示的 PnL 与实际盈亏存在永久偏差。
- **Fix 建议**: LIVE 平仓路径应从 broker 获取最近成交历史（`exchange.fetch_my_trades(symbol)` 或 `fetch_orders(symbol)` 过滤最近 closed 止损单），以实际成交价作为 `exit_price`。如 broker 无法查到，至少在 `error_context` 中标记 `"exit_price_source": "monitor_tick"` 使审计可见。
- **测试建议**: 集成测试（testnet）：开仓后设置 SL，等待 SL 触发，检查 `positions_v5.exit_price` 与 testnet 订单历史的成交价偏差是否在可接受范围（如 0.1%）内。

---

## Finding 15: useV5ActivePositions 用 Promise.all 并行拉取，任一失败则两类持仓均不可见

- **位置**: `Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts:15`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `useV5ActivePositions` 的 `queryFn` 使用 `Promise.all([live, paper])` 同时请求 `/api/v5/positions?status=OPEN` 和 `/api/v5/paper-positions?status=OPEN`。若任一请求失败（如 LIVE 端点 503 或 paper 端点超时），整个 `Promise.all` rejected，React Query 将整个查询标记为错误，`data` 变为 `undefined`，Dashboard 的活仓表格渲染空白或错误状态，而另一类仓位实际是可用的。
- **Failure scenario**: API 服务器重启中，`/api/v5/positions?status=OPEN`（LIVE 端点）返回 503，但 `/api/v5/paper-positions` 正常。`Promise.all` 因 LIVE 请求失败而 reject，Dashboard 显示"加载失败"，操作员看不到任何纸面持仓，虽然纸面仓位运行正常。
- **Fix 建议**: 改为 `Promise.allSettled` 并降级处理：
  ```ts
  const [liveResult, paperResult] = await Promise.allSettled([
    apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
  ]);
  const live = liveResult.status === 'fulfilled' ? liveResult.value.data : [];
  const paper = paperResult.status === 'fulfilled' ? paperResult.value.data : [];
  ```
  同时向 `CombinedActive` 接口添加 `live_error` / `paper_error` 字段，便于前端显示降级提示。
- **测试建议**: 单测（msw mock）：live 接口返回 503，paper 接口返回 200，断言 `combined` 只包含 paper 数据且 `live_error` 有值；页面不显示全局 error 而是只对 live 部分显示降级提示。

---

## Finding 16: DashboardPage 24h PnL 统计仅来自 paper_trades，LIVE 模式结果完全错误

- **位置**: `Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts:27`
- **置信度**: CONFIRMED
- **优先级**: P1
- **描述**: `useV5Dashboard.queryFn` 第 27 行请求 `/api/v5/paper-positions?status=CLOSED&limit=500` 作为 history 数据源。无论系统处于 SHADOW 还是 LIVE 模式，24h PnL、胜率、持仓时长等指标均来自 `paper_trades`，`positions_v5`（LIVE 实仓记录）的历史数据从未被读取。LIVE 模式下 Dashboard 展示的 24h 收益是纸面数字。
- **Failure scenario**: 切换至 LIVE 模式后，LIVE 交易产生实际 PnL，但 Dashboard 显示的 "24h 实现 PnL" 和 "胜率" 来自同期的纸面交易，操作员无法通过 Dashboard 判断 LIVE 交易表现，可能据此做出错误的风控决策。
- **Fix 建议**: 在 `useV5Dashboard` 或对应 API 端点中，根据当前 `system_mode` 路由到正确的数据源：SHADOW → `paper-positions`，LIVE → `positions`（`positions_v5`）。可以通过 `useSystemMode()` 获取当前模式后决定请求哪个端点，或让后端 `/api/v5/dashboard/summary` 端点内部处理路由。
- **测试建议**: 集成测试：在 `positions_v5` 插入若干 CLOSED LIVE 记录，将 `system_settings.system_state` 设为 LIVE，调用 dashboard hook 或 API，断言返回的 `pnl_total_usdt` 来自 `positions_v5` 而非 `paper_trades`。

---

## 四、P2 Findings（体验 / 维护性）

---

## Finding 17: _resolve_leverage() 裸 except Exception: pass 静默丢弃所有错误

- **位置**: `scripts/paper_position_manager.py:87`
- **置信度**: PLAUSIBLE
- **优先级**: P2
- **描述**: `PaperPositionManager._resolve_leverage()` 在 `try` 块（第 77-86 行）调用 `get_exchange_config_manager()` 和 `mgr.get_config()`。第 87 行 `except Exception: pass` 捕获所有异常且不记录。函数继续落入 env 变量检查。如果 exchange config 模块本身有 bug（AttributeError、ImportError、DB OperationalError），该错误被完全掩盖。
- **Failure scenario**: `exchange_config_manager.get_exchange_config_manager()` 在数据库迁移期间抛出 `sqlite3.OperationalError`（表不存在）。异常被吞掉，函数读取 `os.environ.get("OKX_LEVERAGE")` 或最终返回默认值 10。若实际配置是 `leverage=3`（轻仓），paper trade 将以 10× 杠杆计算 size，虚拟仓位比预期大 3.3×，KPI 统计失真。
- **Fix 建议**: 将 `except Exception: pass` 改为记录警告：
  ```python
  except Exception as e:
      print(f"[PaperPositionManager] _resolve_leverage DB 读取失败,回退到 env/default: {e}")
  ```
- **测试建议**: 单测：mock `get_exchange_config_manager` 抛 `AttributeError`，调 `_resolve_leverage()`，断言返回 10（或 env 值）且标准输出包含警告信息。

---

## Finding 18: SettingsPage 同时活仓上限 TextInput 无 onChange 处理器，用户输入无法保存

- **位置**: `Rabbit Hunterfronted/components/pages-v4/SettingsPage.tsx:219`
- **置信度**: CONFIRMED
- **优先级**: P2
- **描述**: SettingsPage 第 219 行的"同时活仓上限"字段渲染为 `<TextInput value="3" />`，没有 `onChange` 属性。用户在输入框修改数值后，值会被 React 受控组件重置（因为 value 是静态字符串），或者修改无法被捕获并通过 `patch.mutate` 保存到 `system_settings`。操作员以为修改了 `v5_max_concurrent` 但实际无效。
- **Failure scenario**: 操作员将"同时活仓上限"从 3 改为 1（希望减少并发持仓），输入框外观上似乎接受了输入，但没有 onChange 触发 patch.mutate，刷新后显示回 3，后端 `v5_max_concurrent` 未变。操作员不知道配置未生效。
- **Fix 建议**: 
  1. 添加受控 state 和 onChange 处理器：
     ```tsx
     const [maxConcurrent, setMaxConcurrent] = useState(settings?.max_concurrent ?? 3);
     // ...
     <TextInput value={String(maxConcurrent)} onChange={(v) => setMaxConcurrent(Number(v))} />
     ```
  2. 在 onBlur 或一个"保存"按钮中调 `patch.mutate({ max_concurrent: maxConcurrent })`
  3. 后端 `SettingsPatchRequest` 和 `patch_settings` 需同步支持 `max_concurrent` 字段写入 `v5_params` 表
- **测试建议**: UI 测试（testing-library）：修改输入框值，断言 `patch.mutate` 被调用且参数中包含 `max_concurrent`。

---

## Finding 19: BacktestPage useEffect 缺少 selectedReport 依赖，可能导致 stale 闭包

- **位置**: `Rabbit Hunterfronted/components/pages-v4/BacktestPage.tsx:146`
- **置信度**: PLAUSIBLE
- **优先级**: P2
- **描述**: BacktestPage 第 146-150 行的 useEffect 依赖数组为 `[jobQuery.data?.status, jobQuery.data?.report_name]`，但 effect 内读取了 `selectedReport`（未列入依赖）。React 的 exhaustive-deps lint 规则会报告此问题。若 `selectedReport` 在 effect 创建后被外部更新，effect 内读取的是旧的 closure 值，条件 `selectedReport !== jobQuery.data.report_name` 可能产生错误结果（阻止或重复触发 report 选择）。
- **Failure scenario**: 用户在 job 完成前手动选择另一个报告（`selectedReport` 变为 `"wf_xyz.json"`），job 完成后 effect 内 `selectedReport` 仍为闭包值 `null`，条件 `null !== 'wf_abc.json'` 为 true，强制覆盖用户的手动选择，切换到 job 报告。
- **Fix 建议**: 将 `selectedReport` 加入依赖数组：
  ```tsx
  }, [jobQuery.data?.status, jobQuery.data?.report_name, selectedReport]);
  ```
  或使用 `useRef` 保存 `selectedReport` 的最新值以在 effect 内访问，避免重复触发。
- **测试建议**: ESLint `react-hooks/exhaustive-deps` 规则启用后该行会直接报错。单测：模拟用户手动选择报告后 job 完成，断言 `selectedReport` 保持用户选择值而非被 job 报告覆盖。

---

## Finding 20: useV5Dashboard 每 30s 拉取 2000 条信号 + 500 条历史，在客户端做全量聚合

- **位置**: `Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts:26`
- **置信度**: CONFIRMED
- **优先级**: P2
- **描述**: `useV5Dashboard.queryFn` 同时请求 `'/api/v5/signals?limit=2000'`（信号原始数据）和 `'/api/v5/paper-positions?status=CLOSED&limit=500'`（历史仓位）并在客户端通过 `Array.filter`/`reduce` 计算 24h 聚合指标。每 30s 刷新一次，每次传输约 2500 行 JSON 数据，客户端 CPU 做完整聚合计算。
- **Failure scenario**: 运行 3 个月后 `trade_scores_v5` 可能有 10 万行，API 端的 `LIMIT 2000` 只截取最新 2000 条，但当日信号超过 2000 时 24h 过滤后的数量计算不准确（漏掉超出 limit 的当日信号）。同时每次 30s 刷新网络传输量约 1-3 MB（取决于 JSON size），在移动网络下体验差。
- **Fix 建议**: 在后端新增聚合端点 `GET /api/v5/dashboard/summary?hours=24`，返回预计算的 `{ signals_24h, passed, executed, win_rate, pnl_sum, avg_hold_minutes }`，不传输原始行。前端只拿摘要数据（< 1 KB）。`closed_24h` 列表仅在需要展开时按需拉取。
- **测试建议**: 后端单测：插入跨越 24h 边界的 3000 条 signals 和 100 条 closed trades，调用 summary 端点，断言返回值与预期的边界内计数一致。

---

## Finding 21: useV5WebSocket 断开重连后不主动刷新查询缓存，数据可能陈旧

- **位置**: `Rabbit Hunterfronted/hooks/useV5WebSocket.ts:95`
- **置信度**: PLAUSIBLE
- **优先级**: P2
- **描述**: `useV5WebSocket` 的 `ws.onclose` 处理器（第 95-103 行）仅递增 `unhealthyCount` 并安排重连定时器，不触发任何 `queryClient.invalidateQueries`。在断开期间发生的后端事件（开仓、平仓、设置变更）通过 WS 广播，但客户端已断线无法接收。重连后，query cache 中的 active positions / dashboard data 等信息仍为断线前的旧快照，直到下次 30s 定时 refetch 才刷新，最多有 30s 数据陈旧窗口。
- **Failure scenario**: WS 断线 25s 后重连。断线期间有一个仓位被 SL 触发关闭。重连后 Dashboard 仍显示该仓位为 OPEN（旧 cache），下次 refetch 在 5s 后（activePositions refetchInterval=5000ms），但 dashboard refetch 在 30s 后。操作员可能在 5-30s 窗口内看到不一致的仓位状态。
- **Fix 建议**: 在 `ws.onopen` 回调中（重连成功时）主动 invalidate 关键查询：
  ```ts
  ws.onopen = () => {
    attemptRef.current = 0;
    // 重连后刷新可能在断线期间变化的数据
    qc.invalidateQueries({ queryKey: ['v5', 'active'] });
    qc.invalidateQueries({ queryKey: ['v5', 'dashboard'] });
    // ...
  };
  ```
- **测试建议**: 单测（msw + fake WebSocket）：模拟 WS 断开后重连，断言 `queryClient.invalidateQueries` 被调用且 active positions 随后触发 refetch。

---

## 五、Phase 0 tech-debt.md 十条落位表

| Phase 0 编号 | 原标题 | 本次编号 | 优先级 | Fix 建议摘要 |
|---|---|---|---|---|
| 1 | LOCAL_DB_PATH vs DB_PATH 命名分裂 | Finding 6 | P1 | `_db_path()` 改读 `DB_PATH` env var |
| 2 | SL_TP_FAIL_OPEN 模块常量不随 Settings UI 变化 | Finding 1 | P0 | 每次开仓时从 DB `system_settings` 实时读取（参考 `_ai_fail_open(db_path)` 模式） |
| 3 | close_position 吞掉 broker 失败后仍标 CLOSED | Finding 2 | P0 | broker 失败时标 `ERROR_RECONCILE_NEEDED` 而非 `CLOSED`；瞬时错误 re-raise |
| 4 | preview 端点从 0 行 ai_training_data 读胜率 | Finding 7 | P1 | 改查 `paper_trades` 或 `trade_scores_v5` 做真实历史胜率计算 |
| 5 | get_param() 吞掉 DB 查询错误，无日志 | Finding 8 | P1 | `except Exception: print(WARN ...)` 替代 `pass` |
| 6 | walkforward daemon 线程状态卡死 | Finding 9 | P1 | API 启动时清理超时 `running`/`queued` job |
| 7 | _resolve_leverage() 裸 except pass | Finding 17 | P2 | `except Exception: print(WARN ...)` |
| 8 | V5Scorer 外层异常兜底静默丢弃 item | Finding 10 | P1 | 写 `block_reason='INTERNAL_ERROR'` 记录而非完全丢弃 |
| 9 | max_concurrent 检查与 open_position 不原子 | Finding 11 | P1 | `BEGIN IMMEDIATE` 事务内二次 count 检查 |
| 10 | LIVE 余额拉取失败回退到 paper 余额 | Finding 3 | P0 | 失败时返回 `None`，scorer 写 `BALANCE_UNAVAILABLE` 并跳过开仓 |

---

## 六、附录：本次未覆盖模块（盲区）

以下模块本次未读或仅做浅扫，不在本清单的覆盖范围内：

| 模块 | 原因 |
|---|---|
| `scripts/*_deprecated.py`（V4.x 遗留）| 已计入 `dead-code-and-tables.md`，无活跃调用路径 |
| `Rabbit Hunterfronted/components/ui/`（通用 UI 组件）| 无交易逻辑，不影响资金安全 |
| `scripts/ai/local_rag.py` | deprecated LR 兜底，被 `trading_assistant.py` 的 vector store 路径替代 |
| `api/routes/v5_charts.py`, `v5_m9.py`, `v5_funding.py` | 只读/展示型路由，本次仅看 endpoint 签名，未深读实现 |
| `scripts/tasks/v5_funding_collector.py` | 仅做行情数据采集，无开/平仓逻辑 |
| `scripts/tasks/paper_monitor.py` | V4.3 兼容路径，V5 路由已走 `V5PositionMonitor`，未深读 |
| `Rabbit Hunterfronted/components/pages-v4/OverviewPage.tsx` / `HistoryPage.tsx` | 未深读，仅确认路由挂载存在 |
| `scripts/ai/trading_assistant.py` | AI 层 prompt/retry 逻辑，未作为本次 bug audit 重点 |
| `scripts/local_db.py` | 数据库 schema 初始化，本次仅查看 anchor 列出的 except 块 |
