#!/usr/bin/env python3
"""模型推进状态的唯一入口（interfaces.md §4.2）。

推进到 _in_progress 时检查必需输入；推进到 _done 时检查必需输入和输出，再执行节点校验命令。
重开必须加 --reopen 和 --reason。省略 --workspace 时读 PLUGIN_WORKSPACE + PROJECT_DIR，省略 --feature 时读 FEATURE_ID。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.common import engine, query  # noqa: E402
from runtime.common.cli import execute  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", "-c", required=True)
    parser.add_argument("--feature", "-f")
    parser.add_argument("--workspace", "-w")
    parser.add_argument("--project")
    parser.add_argument("--reopen", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="兼容参数；始终输出 JSON")
    args = parser.parse_args()
    return execute(lambda: engine.transition(
        query.resolve_project(args.workspace, args.project), query.resolve_feature(args.feature), args.checkpoint,
        reopen=args.reopen, reason=args.reason, dry_run=args.dry_run, owner=args.owner, iteration=args.iteration))


if __name__ == "__main__":
    sys.exit(main())
