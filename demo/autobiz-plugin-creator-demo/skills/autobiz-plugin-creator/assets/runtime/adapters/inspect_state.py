#!/usr/bin/env python3
"""DevClaw 的 project_status / feature_status：输出看板 JSON，只读（interfaces.md §3.3.3、§3.3.4）。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.adapters import board_view  # noqa: E402
from runtime.common import query  # noqa: E402
from runtime.common.cli import execute  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=["project", "run"], required=True)
    parser.add_argument("--workspace", help="项目集合工作区；不带 --project 时为项目目录本身")
    parser.add_argument("--project", help="run 模式的项目目录名")
    parser.add_argument("--projects", nargs="*", default=[], help="project 模式的项目目录名，可多个")
    parser.add_argument("--feature", help="run 模式的 Feature，默认读 FEATURE_ID")
    args = parser.parse_args()

    def inspect():
        if args.mode == "run":
            project = query.resolve_project(args.workspace, args.project)
            return board_view.run_payload(project, query.resolve_feature(args.feature))
        if args.projects:
            projects = {name: board_view.project_runs(query.resolve_project(args.workspace, name))
                        for name in args.projects}
        else:
            project = query.resolve_project(args.workspace, args.project)
            projects = {args.project or project.name: board_view.project_runs(project)}
        return {"workflow": board_view.workflow_shell(), "projects": projects}
    return execute(inspect)


if __name__ == "__main__":
    sys.exit(main())
