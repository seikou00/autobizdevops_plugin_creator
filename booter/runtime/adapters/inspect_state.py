"""DevClaw 的 project_status、feature_status：只读查询看板数据（interfaces.md §3.3.3、§3.3.4）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.adapters import board_view  # noqa: E402
from runtime.common import cli, query  # noqa: E402


def project_entry(workspace, name):
    try:
        return board_view.project_runs(query.resolve_project(workspace, name))
    except query.BoardError as error:
        return {"runs": [], "errors": [str(error)]}


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="查询项目与 Feature 的看板数据")
    parser.add_argument("--mode", choices=("project", "run"), required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--project")
    parser.add_argument("--projects", nargs="*", default=[])
    parser.add_argument("--feature")

    def action():
        args = parser.parse_args(argv)
        workflow = board_view.workflow_payload()
        if args.mode == "run":
            project = query.resolve_project(args.workspace, args.project)
            return {"workflow": workflow, "run": board_view.run_payload(project, query.resolve_feature(args.feature))}
        names = list(args.projects) or ([args.project] if args.project else [])
        return {"workflow": workflow, "projects": {name: project_entry(args.workspace, name) for name in names}}

    return cli.run(action)


if __name__ == "__main__":
    sys.exit(main())
