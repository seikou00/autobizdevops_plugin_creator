#!/usr/bin/env python3
"""DevClaw 的 create_feature：初始化 Feature，项目未初始化时一并初始化（interfaces.md §3.3.2）。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.common import engine, query  # noqa: E402
from runtime.common.cli import execute  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--workspace", help="项目集合工作区；不带 --project 时为项目目录本身")
    parser.add_argument("--project", help="项目目录名")
    parser.add_argument("--feature", help="Feature 名，默认读 FEATURE_ID")
    parser.add_argument("--selected-deployUnit", default="", help="接受但不持久化，发布单元在每次会话时由宿主重新传入")
    parser.add_argument("--workflow-template", default="standard")
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    args = parser.parse_args()
    return execute(lambda: engine.init_feature(
        query.resolve_project(args.workspace, args.project), query.resolve_feature(args.feature),
        owner=args.owner, iteration=args.iteration, template=args.workflow_template))


if __name__ == "__main__":
    sys.exit(main())
