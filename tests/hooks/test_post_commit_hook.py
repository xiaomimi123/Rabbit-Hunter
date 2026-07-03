"""Integration test: real git commit triggers hook and updates dev-log.

Run: pytest tests/hooks/test_post_commit_hook.py -v
Slower than unit tests (spawns git); marked as integration.
"""
import os
import subprocess
import sys
from pathlib import Path

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
