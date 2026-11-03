"""DevClaw 的 create_project：初始化项目的元数据目录（interfaces.md §3.3.1）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.adapters import board_events  # noqa: E402
from runtime.common import cli, engine, query  # noqa: E402


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="初始化项目（create_project）")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--project", required=True)
    holder = {}

    def action():
        args = parser.parse_args(argv)
        project = query.resolve_project(args.workspace, args.project)
        result = engine.init_project(project)
        holder.update(project=project, seq=result.pop("boardSeq"))
        return result

    code = cli.run(action)
    if code == 0:
        board_events.push(holder["project"], None, "create_project", holder["seq"])
    return code


if __name__ == "__main__":
    sys.exit(main())
