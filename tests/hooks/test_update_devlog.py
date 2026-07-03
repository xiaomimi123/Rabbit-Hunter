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
