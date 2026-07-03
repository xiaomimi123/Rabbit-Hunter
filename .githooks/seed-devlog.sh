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
