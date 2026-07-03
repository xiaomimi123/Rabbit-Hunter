# Phase 2 · dev-log 自动记录机制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 post-commit git hook，把每个 commit 自动 append 一行到 in-repo `docs/dev-log.md`。用 Python 3 stdlib（无 pip package）做插入逻辑，bash 做 git 数据采集，pytest + subprocess 做测试。

**Architecture:** 分层：`.githooks/post-commit` bash 采集 SHA/subject/date/stats → 调 `.githooks/lib/update_devlog.py` 做 markdown 插入 → 写回 `docs/dev-log.md`。seed 脚本走同一个 Python 入口，只是循环调用。core.hooksPath 一次性配置激活。

**Tech Stack:** bash 3.2+ / Python 3.9+ stdlib（argparse, pathlib, re, datetime）/ pytest（现有 infra）/ subprocess for integration tests。**无新增 pip 依赖。**

## Global Constraints

- **无新增 pip package** —— 只用 Python stdlib
- **hook 必须 < 200ms** —— 单 commit 无感知延迟
- **hook 必须 `set -e`** —— 失败可见，不吞
- **idempotent**：同 SHA 已存在则跳过 append（不产生重复行）
- **格式锁定**：`- YYYY-MM-DD · \`sha7\` · +N/-M · <full subject>`（中点 `·` 分隔，4 段）
- **月份 header**：`## YYYY-MM`，新月在顶，同月内新条目在顶
- **文件路径固定**：`docs/dev-log.md`（本 spec 唯一 log 文件）
- **hook 脚本路径固定**：`.githooks/post-commit`，`.githooks/lib/update_devlog.py`，`.githooks/seed-devlog.sh`
- **激活方式固定**：`git config core.hooksPath .githooks`（本地 git config，不随 clone 同步）
- **不动**：`CHANGELOG.md`（人工筛选版，本机制不触碰）
- **首次 seed 覆盖 `ad19ca1..HEAD`**，即 v0.5.0 之后全部 commits

---

## File Structure

**新建：**
| 路径 | 职责 |
|---|---|
| `.githooks/post-commit` | bash 入口，采集 git 数据 + 调 update_devlog.py |
| `.githooks/lib/update_devlog.py` | 单条 entry 的插入逻辑（stdlib only） |
| `.githooks/seed-devlog.sh` | 一次性 seed 全部历史 commits |
| `.githooks/README.md` | 目录用途 + 激活说明 1 段 |
| `CLAUDE.md` | 新建，含 dev-log 激活说明 + amend/no-verify caveat |
| `tests/hooks/__init__.py` | 空文件，pytest 识别包 |
| `tests/hooks/test_update_devlog.py` | 单元测试 update_devlog.py |
| `tests/hooks/test_post_commit_hook.py` | 集成测试：tmp git repo + real commit |
| `tests/hooks/test_seed_devlog.py` | 集成测试：seed 脚本 |

**改动：**
| 路径 | 动作 |
|---|---|
| `docs/dev-log.md` | seed 生成后，每次 commit 更新 |
| `README.md` | 加 1 小段指向 CLAUDE.md 的 setup |

---

# Task 1: `update_devlog.py` + post-commit hook + 单元测试

**Files:**
- Create: `.githooks/post-commit`（可执行 bash）
- Create: `.githooks/lib/update_devlog.py`（Python 3 stdlib）
- Create: `tests/hooks/__init__.py`
- Create: `tests/hooks/test_update_devlog.py`（pytest）
- Create: `tests/hooks/test_post_commit_hook.py`（pytest + subprocess）

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - Python module `update_devlog.py` with function `insert_entry(log_path: pathlib.Path, sha7: str, subject: str, date: str, stats: str) -> None`. `date` is `YYYY-MM-DD` string, `stats` is `+N/-M` string. Idempotent by sha7.
  - CLI: `python3 .githooks/lib/update_devlog.py --log-file docs/dev-log.md --sha SHA7 --subject "..." --date YYYY-MM-DD --stats "+N/-M"`
  - `.githooks/post-commit` reads current HEAD via git and shells out to the CLI above

- [ ] **Step 1: 建目录 + 空 test 包**

```bash
mkdir -p .githooks/lib tests/hooks
touch tests/hooks/__init__.py
```

- [ ] **Step 2: 写 test_update_devlog.py（失败 test 集）**

写入 `tests/hooks/test_update_devlog.py`：

```python
"""Unit tests for .githooks/lib/update_devlog.py.

Run: pytest tests/hooks/test_update_devlog.py -v
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_DEVLOG = REPO_ROOT / ".githooks" / "lib" / "update_devlog.py"

# Header used at top of an empty dev-log
EXPECTED_HEADER = (
    "# Rabbit-Hunter Dev Log\n"
    "\n"
    "> 每个 git commit 自动 append。post-commit hook 生成，无人工整理。\n"
    "> 与 CHANGELOG.md 的区别：CHANGELOG 是筛选后的人可读版本；"
    "dev-log 是全部 commit 的机器可读时间线。\n"
    "\n"
)


def run_cli(log_path, sha7, subject, date, stats):
    """Invoke the CLI as a subprocess (matches real hook usage)."""
    return subprocess.run(
        [
            sys.executable, str(UPDATE_DEVLOG),
            "--log-file", str(log_path),
            "--sha", sha7,
            "--subject", subject,
            "--date", date,
            "--stats", stats,
        ],
        capture_output=True, text=True, check=True,
    )


def test_creates_log_with_header_when_missing(tmp_path):
    log = tmp_path / "dev-log.md"
    assert not log.exists()
    run_cli(log, "abc1234", "feat: first", "2026-07-03", "+5/-0")
    content = log.read_text()
    assert content.startswith(EXPECTED_HEADER)


def test_first_entry_creates_month_header(tmp_path):
    log = tmp_path / "dev-log.md"
    run_cli(log, "abc1234", "feat: first", "2026-07-03", "+5/-0")
    content = log.read_text()
    assert "## 2026-07\n" in content
    assert "- 2026-07-03 · `abc1234` · +5/-0 · feat: first\n" in content


def test_second_entry_same_month_prepended(tmp_path):
    log = tmp_path / "dev-log.md"
    run_cli(log, "aaa0001", "feat: older", "2026-07-01", "+1/-0")
    run_cli(log, "bbb0002", "feat: newer", "2026-07-02", "+2/-0")
    content = log.read_text()
    # Newer entry appears BEFORE older within same month
    idx_newer = content.index("bbb0002")
    idx_older = content.index("aaa0001")
    assert idx_newer < idx_older


def test_new_month_prepended_above_older_months(tmp_path):
    log = tmp_path / "dev-log.md"
    run_cli(log, "jun0001", "feat: june thing", "2026-06-15", "+3/-0")
    run_cli(log, "jul0001", "feat: july thing", "2026-07-01", "+3/-0")
    content = log.read_text()
    idx_jul_header = content.index("## 2026-07")
    idx_jun_header = content.index("## 2026-06")
    assert idx_jul_header < idx_jun_header


def test_idempotent_same_sha_no_dup(tmp_path):
    log = tmp_path / "dev-log.md"
    run_cli(log, "abc1234", "feat: first", "2026-07-03", "+5/-0")
    run_cli(log, "abc1234", "feat: first", "2026-07-03", "+5/-0")
    content = log.read_text()
    # sha7 appears only once
    assert content.count("abc1234") == 1


def test_entry_format_exact(tmp_path):
    log = tmp_path / "dev-log.md"
    run_cli(log, "1eb344d", "docs: final review fixes", "2026-07-03", "+25/-24")
    content = log.read_text()
    expected_line = "- 2026-07-03 · `1eb344d` · +25/-24 · docs: final review fixes\n"
    assert expected_line in content


def test_month_header_stays_after_intro_paragraph(tmp_path):
    """The intro blockquote must remain immediately after title; month headers follow."""
    log = tmp_path / "dev-log.md"
    run_cli(log, "abc1234", "feat: X", "2026-07-03", "+1/-0")
    content = log.read_text()
    # Header line 1 = title, then blank, then blockquote (2 lines), then blank, then ## 2026-07
    lines = content.split("\n")
    assert lines[0] == "# Rabbit-Hunter Dev Log"
    assert lines[1] == ""
    assert lines[2].startswith("> 每个 git commit")
    assert lines[3].startswith("> 与 CHANGELOG.md")
    assert lines[4] == ""
    assert lines[5] == "## 2026-07"
```

- [ ] **Step 3: 跑 test，确认全部 FAIL（RED）**

Run: `pytest tests/hooks/test_update_devlog.py -v`
Expected: 7 tests, all FAIL with `FileNotFoundError` or similar（.githooks/lib/update_devlog.py 尚未存在）

- [ ] **Step 4: 写 update_devlog.py（最小实现让 test 过）**

写入 `.githooks/lib/update_devlog.py`：

```python
#!/usr/bin/env python3
"""Insert a single commit entry into docs/dev-log.md, idempotent by sha7.

Called by:
  - .githooks/post-commit (once per commit)
  - .githooks/seed-devlog.sh (many times, one per historical commit)

Constraints (from spec §Global Constraints):
  - Python stdlib only, no pip deps.
  - Idempotent: same sha7 → no duplicate line.
  - Entry format: '- YYYY-MM-DD · `sha7` · +N/-M · <subject>'
  - Month headers: '## YYYY-MM', newest month on top.
  - Within a month, newest entry on top.
"""
import argparse
import re
from pathlib import Path

HEADER = (
    "# Rabbit-Hunter Dev Log\n"
    "\n"
    "> 每个 git commit 自动 append。post-commit hook 生成，无人工整理。\n"
    "> 与 CHANGELOG.md 的区别：CHANGELOG 是筛选后的人可读版本；"
    "dev-log 是全部 commit 的机器可读时间线。\n"
    "\n"
)


def _ensure_header(log_path: Path) -> str:
    """Return current contents; create with header if file missing."""
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(HEADER, encoding="utf-8")
    return log_path.read_text(encoding="utf-8")


def insert_entry(
    log_path: Path, sha7: str, subject: str, date: str, stats: str
) -> None:
    """Insert one entry into log_path. Idempotent by sha7."""
    content = _ensure_header(log_path)

    # Idempotency check: if this exact sha7 already appears in the log, skip.
    if re.search(rf"`{re.escape(sha7)}`", content):
        return

    month = date[:7]  # YYYY-MM
    month_header = f"## {month}"
    entry_line = f"- {date} · `{sha7}` · {stats} · {subject}"

    # Split into header block + body.
    # Header block = everything through the trailing blank line after intro (5 lines).
    lines = content.split("\n")
    # HEADER has 5 lines + trailing empty from split (title, "", intro1, intro2, "").
    # Everything after index 4 (i.e. the blank line at index 4) is body.
    intro_end = 5  # first body line index
    intro = lines[:intro_end]
    body = lines[intro_end:]

    # Reconstruct body: find or create month section.
    body_text = "\n".join(body)
    if month_header not in body_text:
        # Insert new month at top of body.
        body_text = f"{month_header}\n\n{entry_line}\n\n{body_text.lstrip()}"
    else:
        # Find month header line, insert entry immediately after (with blank line skip).
        pattern = re.compile(
            rf"({re.escape(month_header)}\n\n)", re.MULTILINE
        )
        body_text = pattern.sub(rf"\1{entry_line}\n", body_text, count=1)

    new_content = "\n".join(intro) + "\n" + body_text
    # Ensure single trailing newline.
    new_content = new_content.rstrip("\n") + "\n"
    log_path.write_text(new_content, encoding="utf-8")


def _cli():
    p = argparse.ArgumentParser(description="Append one commit entry to dev-log.md")
    p.add_argument("--log-file", required=True, type=Path)
    p.add_argument("--sha", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--stats", required=True, help="+N/-M")
    args = p.parse_args()
    insert_entry(args.log_file, args.sha, args.subject, args.date, args.stats)


if __name__ == "__main__":
    _cli()
```

- [ ] **Step 5: 跑 test，确认 PASS（GREEN）**

Run: `pytest tests/hooks/test_update_devlog.py -v`
Expected: 7 tests all PASS

若某 test 失败，看第一个失败的具体信息，通常是月份 header 插入位置的 off-by-one；修 `body_text` 拼接的空行数量即可。

- [ ] **Step 6: 写 test_post_commit_hook.py（集成测试）**

写入 `tests/hooks/test_post_commit_hook.py`：

```python
"""Integration test: real git commit triggers hook and updates dev-log.

Run: pytest tests/hooks/test_post_commit_hook.py -v
Slower than unit tests (spawns git); marked as integration.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SRC = REPO_ROOT / ".githooks" / "post-commit"
UPDATE_DEVLOG_SRC = REPO_ROOT / ".githooks" / "lib" / "update_devlog.py"


def _init_temp_repo(tmp_path: Path) -> Path:
    """Init a git repo in tmp_path with hooksPath pointing at a copy of our hooks."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    # Copy hooks into a subdir of the tmp repo and point hooksPath there.
    hooks_dir = tmp_path / ".githooks"
    (hooks_dir / "lib").mkdir(parents=True)
    (hooks_dir / "post-commit").write_bytes(HOOK_SRC.read_bytes())
    (hooks_dir / "post-commit").chmod(0o755)
    (hooks_dir / "lib" / "update_devlog.py").write_bytes(
        UPDATE_DEVLOG_SRC.read_bytes()
    )
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def _make_commit(repo: Path, filename: str, content: str, message: str):
    (repo / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=repo, check=True)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = "2026-07-03T12:00:00Z"
    env["GIT_COMMITTER_DATE"] = "2026-07-03T12:00:00Z"
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repo, check=True, env=env,
    )


def test_single_commit_appends_entry(tmp_path):
    repo = _init_temp_repo(tmp_path)
    _make_commit(repo, "hello.txt", "hi\n", "feat: hello world")
    log = repo / "docs" / "dev-log.md"
    assert log.exists()
    content = log.read_text()
    assert "feat: hello world" in content
    assert "## 2026-07" in content
    # sha7 line format
    sha7 = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
    ).strip()
    assert f"`{sha7}`" in content


def test_two_commits_newest_on_top(tmp_path):
    repo = _init_temp_repo(tmp_path)
    _make_commit(repo, "a.txt", "1\n", "feat: first")
    _make_commit(repo, "b.txt", "2\n", "feat: second")
    log = (repo / "docs" / "dev-log.md").read_text()
    idx_second = log.index("feat: second")
    idx_first = log.index("feat: first")
    assert idx_second < idx_first


def test_stats_format(tmp_path):
    """Assert +N/-M is parsed correctly from git."""
    repo = _init_temp_repo(tmp_path)
    _make_commit(repo, "a.txt", "line1\nline2\nline3\n", "feat: three lines")
    log = (repo / "docs" / "dev-log.md").read_text()
    # 3 insertions, 0 deletions
    assert "+3/-0" in log
```

- [ ] **Step 7: 跑 integration test，此时会 FAIL（post-commit 未写）**

Run: `pytest tests/hooks/test_post_commit_hook.py -v`
Expected: 3 tests all FAIL —— hook file `.githooks/post-commit` 存在但为空 or 不存在

- [ ] **Step 8: 写 `.githooks/post-commit`**

写入 `.githooks/post-commit`：

```bash
#!/usr/bin/env bash
# post-commit: append this commit to docs/dev-log.md via update_devlog.py.
#
# Spec: docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md
# Activate with: git config core.hooksPath .githooks
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
LOG_FILE="$REPO_ROOT/docs/dev-log.md"
UPDATE="$REPO_ROOT/.githooks/lib/update_devlog.py"

SHA7=$(git rev-parse --short HEAD)
SUBJECT=$(git log -1 --pretty=%s)
DATE=$(git log -1 --pretty=%as)   # ISO short date (YYYY-MM-DD, author-date)

# Compute +N/-M from --numstat (tab-separated: adds\tdels\tpath). Handles binary (-).
STATS=$(
  git show --numstat --format= HEAD \
    | awk 'BEGIN{a=0;d=0} $1!="-" && $2!="-" {a+=$1; d+=$2} END {printf "+%d/-%d", a, d}'
)

python3 "$UPDATE" \
  --log-file "$LOG_FILE" \
  --sha "$SHA7" \
  --subject "$SUBJECT" \
  --date "$DATE" \
  --stats "$STATS"
```

- [ ] **Step 9: 权限位**

```bash
chmod +x .githooks/post-commit
```

- [ ] **Step 10: 跑 integration test，确认全 PASS**

Run: `pytest tests/hooks/test_post_commit_hook.py -v`
Expected: 3 tests PASS

- [ ] **Step 11: 跑全部 hook tests + 性能自查**

```bash
pytest tests/hooks/ -v
```
Expected: 10 tests PASS (7 unit + 3 integration)

性能自查（<200ms 目标）：

```bash
# Time a real commit's post-commit hook manually
cd /tmp && rm -rf perf-test && git init -q perf-test && cd perf-test
git config core.hooksPath /Users/lizhishaoniange/Documents/Rabbit-Hunter/.githooks
echo x > f.txt && git add f.txt
time git commit -m "perf test" 2>&1 | tail -5
# 用户端看 real 时间 < 200ms 视为 OK
```
（性能自查只跑一次，不写死到 test）

- [ ] **Step 12: Commit**

```bash
git add .githooks/ tests/hooks/
git commit -m "$(cat <<'EOF'
feat(devlog): post-commit hook + update_devlog.py + tests

Task 1/4 · Phase 2 mechanism 核心组件。

- .githooks/post-commit: bash 入口，采 SHA/subject/date/stats
- .githooks/lib/update_devlog.py: stdlib-only 插入逻辑
- 10 tests (7 unit + 3 integration), all passing

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Task 2: `seed-devlog.sh` + seed 全部历史

**Files:**
- Create: `.githooks/seed-devlog.sh`（可执行 bash）
- Create: `tests/hooks/test_seed_devlog.py`（pytest + subprocess）
- Modify: `docs/dev-log.md`（seed 后从 0 行到 ≥ 211 rows）

**Interfaces:**
- Consumes: `.githooks/lib/update_devlog.py`（Task 1）—— 同一入口，保证格式一致
- Produces: 完整的 `docs/dev-log.md` 覆盖 `ad19ca1..HEAD`

- [ ] **Step 1: 写 test_seed_devlog.py**

写入 `tests/hooks/test_seed_devlog.py`：

```python
"""Integration test: seed script produces N rows matching git log range.

Run: pytest tests/hooks/test_seed_devlog.py -v
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = REPO_ROOT / ".githooks" / "seed-devlog.sh"
UPDATE_DEVLOG = REPO_ROOT / ".githooks" / "lib" / "update_devlog.py"


def _init_repo_with_commits(tmp_path: Path, n: int) -> Path:
    """Init a repo with n commits, all on 2026-07-01."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@x"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=tmp_path, check=True
    )
    env = {
        "GIT_AUTHOR_DATE": "2026-07-01T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-07-01T12:00:00Z",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    for i in range(n):
        (tmp_path / f"f{i}.txt").write_text(f"{i}\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: commit {i}"],
            cwd=tmp_path, check=True, env=env,
        )
    # Copy seed script + Python module into the tmp repo, mirroring layout.
    (tmp_path / ".githooks" / "lib").mkdir(parents=True)
    (tmp_path / ".githooks" / "seed-devlog.sh").write_bytes(
        SEED_SCRIPT.read_bytes()
    )
    (tmp_path / ".githooks" / "seed-devlog.sh").chmod(0o755)
    (tmp_path / ".githooks" / "lib" / "update_devlog.py").write_bytes(
        UPDATE_DEVLOG.read_bytes()
    )
    return tmp_path


def test_seed_5_commits(tmp_path):
    repo = _init_repo_with_commits(tmp_path, 5)
    # Seed from the first commit's parent (there isn't one) → use --root
    first_sha = subprocess.check_output(
        ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo, text=True
    ).strip()
    subprocess.run(
        ["./.githooks/seed-devlog.sh", first_sha, "HEAD"],
        cwd=repo, check=True,
    )
    log = (repo / "docs" / "dev-log.md").read_text()
    # 5 commits should produce 5 entry lines (the first-sha itself is excluded
    # by the range convention `first..HEAD`; we include the range endpoint).
    entry_lines = [l for l in log.split("\n") if l.startswith("- 2026-")]
    # first..HEAD excludes first, includes commits 2..5 → 4 lines.
    # If the seed script uses `first_sha..HEAD` semantics, expect 4.
    # If it inclusively seeds from first_sha, expect 5.
    # Test expects the git-range convention: exclusive of first_sha, i.e. 4 entries.
    assert len(entry_lines) == 4


def test_seed_ordering_newest_on_top(tmp_path):
    repo = _init_repo_with_commits(tmp_path, 3)
    first_sha = subprocess.check_output(
        ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo, text=True
    ).strip()
    subprocess.run(
        ["./.githooks/seed-devlog.sh", first_sha, "HEAD"],
        cwd=repo, check=True,
    )
    log = (repo / "docs" / "dev-log.md").read_text()
    # Newest commit is "feat: commit 2" (0-indexed), oldest included is
    # "feat: commit 1" (commit 0 = first_sha, excluded).
    idx_2 = log.index("feat: commit 2")
    idx_1 = log.index("feat: commit 1")
    assert idx_2 < idx_1
```

- [ ] **Step 2: 跑 test，FAIL（seed 脚本未写）**

Run: `pytest tests/hooks/test_seed_devlog.py -v`
Expected: 2 tests FAIL

- [ ] **Step 3: 写 `.githooks/seed-devlog.sh`**

写入 `.githooks/seed-devlog.sh`：

```bash
#!/usr/bin/env bash
# seed-devlog: one-time bulk-seed docs/dev-log.md from a git range.
#
# Usage: .githooks/seed-devlog.sh <BASE_SHA> <HEAD_SHA>
#   Uses git range BASE..HEAD (BASE exclusive, HEAD inclusive).
#   Iterates oldest → newest, so newest ends up on top of the log
#   (update_devlog.py always prepends within a month).
#
# Spec: docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md
set -e

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <BASE_SHA> <HEAD_SHA>" >&2
  exit 2
fi

BASE="$1"
HEAD_REF="$2"

REPO_ROOT="$(git rev-parse --show-toplevel)"
LOG_FILE="$REPO_ROOT/docs/dev-log.md"
UPDATE="$REPO_ROOT/.githooks/lib/update_devlog.py"

# List commits oldest → newest (reverse order).
COMMITS=$(git log --reverse --pretty=%H "$BASE..$HEAD_REF")

if [ -z "$COMMITS" ]; then
  echo "no commits in range $BASE..$HEAD_REF" >&2
  exit 0
fi

COUNT=0
for SHA in $COMMITS; do
  SHA7=$(git rev-parse --short "$SHA")
  SUBJECT=$(git log -1 --pretty=%s "$SHA")
  DATE=$(git log -1 --pretty=%as "$SHA")
  STATS=$(
    git show --numstat --format= "$SHA" \
      | awk 'BEGIN{a=0;d=0} $1!="-" && $2!="-" {a+=$1; d+=$2} END {printf "+%d/-%d", a, d}'
  )
  python3 "$UPDATE" \
    --log-file "$LOG_FILE" \
    --sha "$SHA7" \
    --subject "$SUBJECT" \
    --date "$DATE" \
    --stats "$STATS"
  COUNT=$((COUNT + 1))
done

echo "seeded $COUNT commit(s) into $LOG_FILE"
```

- [ ] **Step 4: 权限位**

```bash
chmod +x .githooks/seed-devlog.sh
```

- [ ] **Step 5: 跑 seed test，PASS**

Run: `pytest tests/hooks/test_seed_devlog.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: 跑真实 seed（`ad19ca1..HEAD`）**

先备份如果存在：
```bash
[ -f docs/dev-log.md ] && mv docs/dev-log.md docs/dev-log.md.bak
```

跑 seed：
```bash
./.githooks/seed-devlog.sh ad19ca1 HEAD
```
Expected: 输出 `seeded N commit(s) into ...`，N 应等于 `git log --oneline ad19ca1..HEAD | wc -l` 的当前值（约 211-215）。

- [ ] **Step 7: 验证 seed 结果**

```bash
# Row count 匹配
COMMIT_COUNT=$(git log --oneline ad19ca1..HEAD | wc -l | tr -d ' ')
ENTRY_COUNT=$(grep -cE "^- [0-9]{4}-[0-9]{2}-[0-9]{2}" docs/dev-log.md)
echo "commits=$COMMIT_COUNT entries=$ENTRY_COUNT"
[ "$COMMIT_COUNT" = "$ENTRY_COUNT" ] || echo "MISMATCH"

# 月份 header 齐全
grep -c "^## 2026-0[6-7]" docs/dev-log.md   # 至少 2（6月+7月）

# 首行 entry 是最新 commit
HEAD_SHA=$(git rev-parse --short HEAD)
head -20 docs/dev-log.md | grep -q "\`$HEAD_SHA\`" && echo "HEAD in first month block: OK"

# 最老 entry 是 ad19ca1 之后的第一个 commit
OLDEST=$(git log --reverse --pretty=%h ad19ca1..HEAD | head -1)
tail -5 docs/dev-log.md | grep -q "\`$OLDEST\`" && echo "oldest entry: OK"
```
Expected: 三条 check 均通过；MISMATCH 不出现。

- [ ] **Step 8: 清理备份**

```bash
rm -f docs/dev-log.md.bak
```

- [ ] **Step 9: Commit**

```bash
git add .githooks/seed-devlog.sh tests/hooks/test_seed_devlog.py docs/dev-log.md
git commit -m "$(cat <<'EOF'
feat(devlog): seed script + seed v0.5.0 之后全部 commits

Task 2/4 · seed-devlog.sh 用与 post-commit 一致的 update_devlog.py，
一次性把 ad19ca1..HEAD 灌进 docs/dev-log.md。行数与 git log 匹配。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Task 3: `.githooks/README.md` + `CLAUDE.md`

**Files:**
- Create: `.githooks/README.md`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: Task 1 (post-commit) + Task 2 (seed) 的存在
- Produces: 文档，无代码接口

- [ ] **Step 1: 写 `.githooks/README.md`**

```markdown
# .githooks/

被 `core.hooksPath` 指向的 git hook 目录。**不要在这里放临时脚本** —— 里面所有可执行文件都会被 git 当 hook 触发。

## 现有文件

- `post-commit`：每个 commit 完成后跑，把这个 commit append 到 `docs/dev-log.md`
- `seed-devlog.sh`：一次性历史 seed，`.githooks/seed-devlog.sh <BASE> <HEAD>`
- `lib/update_devlog.py`：单条 entry 插入逻辑（Python stdlib）

## 激活

```bash
git config core.hooksPath .githooks
```

`core.hooksPath` 是本地 git config，不随 clone 同步。**每台开发机需要跑一次**。

## 详细设计

见 `docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md`。
```

- [ ] **Step 2: 写 `CLAUDE.md`**

```markdown
# Claude Code · Rabbit-Hunter 项目指令

> 项目层 Claude Code instructions。会话开始时自动加载。

## dev-log 机制

**首次启用（每台开发机跑一次）：**

```bash
git config core.hooksPath .githooks
```

激活后每个 `git commit` 会自动 append 一行到 `docs/dev-log.md`。若你 (Claude) 或用户观察到多个 commit 落下但 dev-log 没更新，先检查：

```bash
git config --get core.hooksPath
```

应输出 `.githooks`。若为空，运行上面的激活命令。

## dev-log 使用规范

- `docs/dev-log.md` 是**机器生成的时间线**，覆盖 v0.5.0 之后每个 commit。**不手工编辑**
- 手工筛选 + 主题聚簇的版本走 `CHANGELOG.md`（release-level）
- 需要回顾 v0.5.0 之后某段时间做了什么 → 读 dev-log
- 需要给外部读者讲 v0.5.x → HEAD 的 narrative → 读 / 更新 CHANGELOG

## Amend caveat

`git commit --amend` 会生成新 SHA。post-commit hook 会为 amend 后的新 commit 再 append 一行，**老 SHA 的孤儿 entry 仍在 dev-log**。amend 后请手工去掉孤儿行（搜索老 SHA7 删除对应行）。

## `--no-verify`

`git commit --no-verify` 会跳过 post-commit hook，该 commit 不进 dev-log。当且仅当你 (Claude) 或用户明确要求 opt-out 时使用。

## 相关文档

- 设计: `docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md`
- 实施 plan: `docs/superpowers/plans/2026-07-03-phase2-devlog-mechanism.md`
- 项目结构: `PROJECT_STRUCTURE.md`
```

- [ ] **Step 3: 验证文件存在**

```bash
test -f .githooks/README.md && echo "githooks/README.md: OK"
test -f CLAUDE.md && echo "CLAUDE.md: OK"
```

- [ ] **Step 4: Commit**

```bash
git add .githooks/README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(devlog): .githooks/README.md + CLAUDE.md 激活说明

Task 3/4 · 首次启用需要 git config core.hooksPath .githooks。
CLAUDE.md 含 amend / --no-verify caveats。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Task 4: `README.md` 指向 + 激活 + 验收测试

**Files:**
- Modify: `README.md`（加 1 段指向 CLAUDE.md）
- 无新文件

**Interfaces:**
- Consumes: 前 3 个 task 全部
- Produces: 一次真实的 commit 触发 hook，dev-log 里出现新行

- [ ] **Step 1: 找到 README.md 里合适的位置**

阅读 `README.md`，找"开发环境"、"Setup"或类似的段落。若没有则放在"如何运行"段落之后。

```bash
grep -n "^## \|^### " README.md | head -30
```

- [ ] **Step 2: append 1 段到那个位置**

用 Edit 工具插入：

```markdown
### dev-log 激活（首次 clone 后跑一次）

```bash
git config core.hooksPath .githooks
```

每个 commit 会自动 append 到 `docs/dev-log.md`。详见 `CLAUDE.md § dev-log 机制`。
```

（具体插入位置和上下 anchor 由执行者按现有 README 结构选定）

- [ ] **Step 3: 激活 hooksPath**

```bash
git config core.hooksPath .githooks
git config --get core.hooksPath   # 期望：.githooks
```

- [ ] **Step 4: 空 commit 验收**

```bash
BEFORE=$(wc -l < docs/dev-log.md)
git commit --allow-empty -m "chore: activate devlog hook (acceptance test)"
AFTER=$(wc -l < docs/dev-log.md)
DELTA=$((AFTER - BEFORE))
echo "before=$BEFORE after=$AFTER delta=$DELTA"
[ "$DELTA" -ge 1 ] && echo "acceptance: PASS" || echo "acceptance: FAIL"
```

Expected: `delta=1` (or 3 if a new month header was created)，`acceptance: PASS`。

- [ ] **Step 5: 验证最新 entry 出现在 dev-log 顶部**

```bash
HEAD_SHA=$(git rev-parse --short HEAD)
head -10 docs/dev-log.md | grep -q "\`$HEAD_SHA\`" && echo "head SHA in top block: PASS"
```

- [ ] **Step 6: 跑全部 hook tests 一遍确认没坏**

```bash
pytest tests/hooks/ -v
```
Expected: 12 tests all pass (7 unit + 3 post-commit integration + 2 seed integration)

- [ ] **Step 7: Commit（含 dev-log 的新增行）**

```bash
git add README.md docs/dev-log.md
git commit -m "$(cat <<'EOF'
docs(readme): 指向 CLAUDE.md 的 dev-log 激活说明 + 验收 commit

Task 4/4 · 最后一 task。README 加 1 段激活说明，
配合 acceptance-test 空 commit（Task 4 Step 4）确认端到端正确。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: 最终 push（可选，视用户决定）**

```bash
git push origin main
```

---

# Self-Review 记录

- **Spec § 四 格式**：Task 1 Step 4 update_devlog.py + Task 1 Step 8 post-commit 严格用 `- YYYY-MM-DD · \`sha7\` · +N/-M · <subject>` 4 段格式 ✓
- **Spec § 五 hook 实现**：Task 1 Step 8 展开完整 bash + Python，`set -e`，无网络，Python stdlib ✓
- **Spec § 五 idempotency**：Task 1 Step 2 test + Step 4 实现的 sha7 dedup check ✓
- **Spec § 五 性能约束 < 200ms**：Task 1 Step 11 有手工性能自查（非硬性 fail）✓
- **Spec § 六 Bootstrap**：Task 2 seed 全部历史 + Task 3 CLAUDE.md + Task 4 激活 + 空 commit 验收 ✓
- **Spec § 七 Edge cases**：CLAUDE.md（Task 3 Step 2）含 amend + --no-verify 说明 ✓
- **Spec § 八 CHANGELOG 关系**：CLAUDE.md 内注明 dev-log ≠ CHANGELOG ✓
- **Spec § 九 Failure modes**：CLAUDE.md health check（`git config --get core.hooksPath`）明确 ✓
- **Spec § 十 验收**：Task 4 完成 4 项验收（hook 存在可执行、单 commit 新增 1 行、seed 行数匹配、CLAUDE.md 存在）✓
- **Placeholder scan**：无 TBD / "similar to Task N" / 无空 code block ✓
- **Type consistency**：`insert_entry(log_path, sha7, subject, date, stats)` 签名在 Task 1 定义并被 Task 2 seed 通过同一 CLI 复用 ✓
