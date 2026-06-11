#!/bin/sh
# 一次性 DB 备份脚本 — V5 升级前跑一次。
# 用法:./scripts/backup_pre_v5.sh
set -e
DB=data/rabbit_hunter.db
if [ ! -f "$DB" ]; then
    echo "未找到 $DB,跳过备份"
    exit 0
fi
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="${DB}.backup-pre-v5.${TS}"
cp "$DB" "$BACKUP"
echo "已备份到 $BACKUP"
ls -lh "$BACKUP"
