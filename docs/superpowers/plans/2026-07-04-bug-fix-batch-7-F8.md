# Bug Fix Batch 7 · Finding 8 · get_param DB 错改 WARN 日志 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/v5_params.py:86-87` `except Exception: pass` → `except Exception as e: print(WARN...)`，DB 错时不再静默吞。

**Architecture:** 单 task TDD 循环：先写 1 test（RED —— 现代码不 print WARN）→ 改 1 行 → GREEN → 邻近回归 → 单 commit。

**Tech Stack:** Python stdlib + pytest capsys fixture + monkeypatch。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `scripts/v5_params.py` (modify) + `tests/test_v5_params.py` (append 1 test)
- 改动仅限 L86-87 那 2 行（`except Exception: pass` → `except Exception as e: print(...)`）
- WARN 消息格式 EXACT: `f"[get_param] DB 读取失败,使用默认值 {key}={default}: {type(e).__name__}: {e}"`
- 保留 `return default` fallback（行为兼容）
- 不改：缓存策略、优先级、其他方法、`.githooks/`、dev-log、前端
- 现有 tests 无回归：
  - `test_v5_params.py` 6/6 → 7/7
  - `test_v5_scorer_run_catches.py` 1/1
  - `test_v5_scorer.py` 1/1
  - `test_v5_position_manager.py` 8/8
  - `test_v5_position_monitor.py` 15/3
  - `test_paper_position_manager_v5.py` 4/4
  - `test_settings_db.py` 6/6
  - `test_collector_main_v5.py` 3/3
- Single commit, subject EXACT: `fix(v5_params): get_param() DB 错误改 WARN 日志,不再静默吞 (Finding 8)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/v5_params.py` | Modify L86-87 —— 2 行 |
| `tests/test_v5_params.py` | Append 1 test 到文件末尾 |

---

# Task 1: get_param() WARN 日志 + 1 test

**Files:**
- Modify: `scripts/v5_params.py`
- Modify: `tests/test_v5_params.py`

**Interfaces:**
- Consumes: pytest `capsys` fixture（现有 pytest 装配）+ `monkeypatch`
- Produces: 无新对外 API；`get_param` 语义不变（DB 错仍返 default），只多 print 一行

## RED phase

- [ ] **Step 1: 追加新 test 到 `tests/test_v5_params.py` 末尾**

```python


def test_db_error_logs_warning_and_returns_default(monkeypatch, capsys):
    """DB 层抛异常 → 打印 WARN + 返 default (不再静默,Finding 8)."""
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

- [ ] **Step 2: 跑 test —— 期望 RED**

```bash
python3 -m pytest tests/test_v5_params.py::test_db_error_logs_warning_and_returns_default -v
```

Expected: FAIL —— `assert "[get_param]" in captured.out` 失败（现代码 `except Exception: pass` 什么都不 print）。

**若 test 意外 PASS**：可能是 sqlite3.connect 对 `/nonexistent/dir/x.db` 不抛异常（某些 sqlite 版本行为）。在这种情况下 fallback 到直接 patch `sqlite3.connect`：

```python
def _raiser(_path):
    import sqlite3
    raise sqlite3.OperationalError("db locked")
monkeypatch.setattr("sqlite3.connect", _raiser)
```

## GREEN phase

- [ ] **Step 3: 改 `scripts/v5_params.py:86-87`**

用 Edit 工具（unique substring anchor：`except Exception:\n        pass`）。

**Before**（约 L86-87）：
```python
    except Exception:
        pass
```

**After**：
```python
    except Exception as e:
        print(f"[get_param] DB 读取失败,使用默认值 {key}={default}: {type(e).__name__}: {e}")
```

（不动上下文其他行）

- [ ] **Step 4: 跑 test —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_params.py -v
```

Expected: 7/7 PASS（6 现有 + 1 新）

若失败：
- `assert result == 3` FAIL → 检查是否误改了 `return default` 那行
- `assert "[get_param]" in captured.out` FAIL → 检查 print 前缀
- `assert "DB 读取失败" in captured.out` FAIL → 检查中文字符是否正确
- `assert "v5_max_concurrent" in captured.out` FAIL → 检查 `{key}` 替换

## 邻近回归 + sanity + commit

- [ ] **Step 5: 邻近 tests 无回归**

```bash
python3 -m pytest tests/test_v5_scorer_run_catches.py tests/test_v5_scorer.py tests/test_v5_position_manager.py tests/test_v5_position_monitor.py tests/test_paper_position_manager_v5.py tests/test_settings_db.py tests/test_collector_main_v5.py -v 2>&1 | tail -15
```

Expected: 现有 baseline 完全不变
- test_v5_scorer_run_catches.py 1/1 PASS
- test_v5_scorer.py 1/1 PASS
- test_v5_position_manager.py 8/8 PASS
- test_v5_position_monitor.py 15 PASS / 3 pre-existing FAIL
- test_paper_position_manager_v5.py 4/4 PASS
- test_settings_db.py 6/6 PASS
- test_collector_main_v5.py 3/3 PASS

- [ ] **Step 6: sanity greps**

```bash
# 新 print 存在
grep -n "\[get_param\] DB 读取失败" scripts/v5_params.py
# 期望：1 hit

# 老 except pass 已消失
grep -c "except Exception:$" scripts/v5_params.py
# 期望：0 hits (或若有其他地方还有,不能是原 L86-87 那处)

# 若有其他 except pass 处（get_param 之外的位置）不动
grep -n "except Exception" scripts/v5_params.py
# 期望：仅 1 hit，就是 L86-87 的 `except Exception as e:`
```

- [ ] **Step 7: Commit**

```bash
git add scripts/v5_params.py tests/test_v5_params.py
git commit -m "$(cat <<'EOF'
fix(v5_params): get_param() DB 错误改 WARN 日志,不再静默吞 (Finding 8)

修 bug-fix-list.md Finding 8 (P1):scripts/v5_params.py:86-87
的 except Exception: pass 静默吞 DB 读取错。所有系统参数(RSI 阈值/
SL 乘数/max_concurrent 等)都通过 get_param() 读,DB 锁定时全部
静默回退 default,运营在 StrategyConfig 页配的非默认值失效但无日志。

Change:
- except Exception: pass → except Exception as e: print(WARN)
- 消息格式:[get_param] DB 读取失败,使用默认值 {key}={default}: ...
- 保留 return default fallback(行为兼容)
- 缓存策略/优先级不动

Tests:
- 追加 test_db_error_logs_warning_and_returns_default
  用 monkeypatch _db_path → nonexistent 目录 + capsys 断言 WARN 输出
- 现有 6 tests + 邻近 tests 全无回归

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1 (1 行改)**: Step 3 ✓
- **spec § 五 Change 2 (1 test)**: Step 1 完整 ✓
- **spec § 六 验收**: Step 4 (7/7) + Step 5 (邻近回归) + Step 6 (sanity) ✓
- **spec § 七 失效模式**: 已在 spec 里声明可接受（本 plan 不加 rate-limit）✓
- **placeholder scan**: 无 TBD ✓
- **type consistency**: WARN 消息格式在 spec + plan + test 一致 ✓
- **测试 RED→GREEN**: Step 2 = RED；Step 4 = GREEN ✓
- **atomicity**: 单 commit at Step 7 ✓
