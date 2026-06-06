"""scripts/collector.py — DEPRECATED stub (v45)

Reason: 仓库历史上有两个完整的"采集 + 主循环"实现：
  - scripts/collector.py  (旧 — 2670 行，写 Supabase)
  - scripts/tasks/collector_main.py  (新 — 模块化 scanner/deep_collector/scorer/writer，写 local_db)

两个并存让 bug 修复必须双倍劳动，且新人无法判断"哪个是真的在跑"。
v45 起，唯一受支持的入口是 scripts.tasks.collector_main。
本文件保留为 deprecation stub — 旧代码已移至 scripts/_legacy_collector.py 仅供考古查阅。
"""

import sys


def main() -> int:
    print(
        "─" * 72 + "\n"
        "[DEPRECATED] scripts/collector.py 已被弃用 (v45)。\n"
        "\n"
        "请改用新的模块化入口：\n"
        "    python -m scripts.tasks.collector_main\n"
        "\n"
        "或直接双击 start_collector.bat（已指向新入口）。\n"
        "\n"
        "旧代码已归档到 scripts/_legacy_collector.py（仅供查阅，不再维护）。\n"
        + "─" * 72,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
