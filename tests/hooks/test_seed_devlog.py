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
