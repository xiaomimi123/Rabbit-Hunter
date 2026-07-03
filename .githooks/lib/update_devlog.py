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
