#!/usr/bin/env python3
"""DevClaw 的 create_project：初始化项目，重复执行不会丢失已有进度（interfaces.md §3.3.1）。"""

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
    args = parser.parse_args()
    return execute(lambda: engine.init_project(query.resolve_project(args.workspace, args.project)))


if __name__ == "__main__":
    sys.exit(main())
