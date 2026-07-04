# Bug Fix Batch 7 · Finding 8 · get_param() DB 错误改成 WARN 日志 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 8 (P1)

---

## 一、问题陈述

`scripts/v5_params.py:86-87`：

```python
    except Exception:
        pass
    # 4. default
    return default
```

DB 出问题（锁定、表不存在、权限错等）时静默吞异常。**所有系统参数**（RSI 阈值、SL/TP 乘数、`v5_max_concurrent`、`v5_sl_atr_mult` 等）都通过 `get_param()` 读取，DB 异常时全部悄悄回退到 hardcoded default。运营在 StrategyConfig 页配置的非默认值被静默忽略，日志无任何 WARN。唯一观测手段是对比 trade_scores_v5 中的实际行为与配置页展示。

## 二、目标

改成 audit 建议的 `except Exception as e: print(WARN ...)` —— 打日志，保持行为兼容（return default）。

## 三、范围

**In scope**：
- `scripts/v5_params.py` L86-87 一行改
- `tests/test_v5_params.py` 追加 1 test 覆盖 WARN 日志路径

**Out of scope**：
- 不改缓存策略（正/负缓存都保持）
- 不改 ENV > DB > default 优先级
- 不改其他方法（`invalidate_cache` 等）
- 不改 `print` → `logging.warning`（codebase style 一致用 print）
- 不修其他 P1
- 不动 .githooks / dev-log / 前端

## 四、Change 1 — `scripts/v5_params.py` L86-87

**Before**：
```python
    except Exception:
        pass
    # 4. default
    return default
```

**After**：
```python
    except Exception as e:
        print(f"[get_param] DB 读取失败,使用默认值 {key}={default}: {type(e).__name__}: {e}")
    # 4. default
    return default
```

## 五、Change 2 — `tests/test_v5_params.py` 追加 1 test

```python
def test_db_error_logs_warning_and_returns_default(monkeypatch, capsys):
    """DB 层抛异常 → 打印 WARN + 返 default (不再静默)。"""
    from scripts import v5_params
    v5_params._CACHE.clear()  # 清缓存,让 DB 路径被走
    monkeypatch.delenv("V5_MAX_CONCURRENT", raising=False)
    # DB 路径指向不存在的目录 → sqlite3.connect() 抛 OperationalError
    monkeypatch.setattr(v5_params, "_db_path", lambda: "/nonexistent/dir/x.db")

    result = v5_params.get_param("v5_max_concurrent", 3, int)
    captured = capsys.readouterr()
    assert result == 3
    assert "[get_param]" in captured.out
    assert "DB 读取失败" in captured.out
    assert "v5_max_concurrent" in captured.out
```

**若测试环境 sqlite3 对不存在的目录不抛而是延迟到 execute 时抛**（sqlite3 行为不完全一致），fallback 备选：

```python
    def _raiser(_path):
        import sqlite3
        raise sqlite3.OperationalError("db locked")
    monkeypatch.setattr("sqlite3.connect", _raiser)
```

任选其一都能触发 WARN 路径。

## 六、验收标准

- `python3 -m pytest tests/test_v5_params.py -v` → 7/7 pass（现有 6 + 1 新）
- 邻近 tests 无回归：`test_v5_scorer_run_catches.py`、`test_v5_scorer.py`、`test_v5_position_manager.py`、`test_v5_position_monitor.py`、`test_paper_position_manager_v5.py`、`test_settings_db.py`、`test_collector_main_v5.py`
- `grep -c "except Exception: pass\|except Exception:\s*$" scripts/v5_params.py` → 0（模糊 pattern，一定要看目标那一处已改）
- `grep -n "\[get_param\] DB 读取失败" scripts/v5_params.py` → 1 hit
- 只 stage 2 文件
- Commit subject: `fix(v5_params): get_param() DB 错误改 WARN 日志,不再静默吞 (Finding 8)`

## 七、失效模式

- **DB 短暂锁定 → 恢复**：每次 tick 一条 WARN 日志（可能刷屏），但不缓存错误 → 恢复后正常读。可接受。
- **DB 永久不可用**：每次 tick 都刷 WARN，logs 会撑爆。**下一批可加 rate-limit（YAGNI，本次不做）**。
- **敏感数据泄漏**：`str(e)` 不太可能含密钥（sqlite 错误信息不含 auth 数据）。可接受。

## 八、超范围声明

- 不改缓存 TTL / 策略
- 不改 print → logging
- 不加 rate-limit
- 不改其他 fallback 行为
- 不修其他 P1

## 九、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 8（P1）
- 引用：
  - `scripts/v5_params.py:86-87`（现状 except pass）
  - `scripts/v5_params.py:82-85`（正/负缓存 —— 保持）
