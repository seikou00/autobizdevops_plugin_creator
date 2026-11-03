"""DevClaw 的 create_feature：创建 Feature，项目未初始化时先初始化（interfaces.md §3.3.2）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json  # noqa: E402

from runtime.adapters import board_events  # noqa: E402
from runtime.common import cli, engine, query  # noqa: E402


def parse_units(raw):
    if raw is None:
        return None
    try:
        units = json.loads(raw) if raw.strip() else []
    except ValueError as error:
        raise query.BoardError(f"--selected-deployUnit 不是合法的 JSON 数组: {error}") from None
    if not isinstance(units, list):
        raise query.BoardError("--selected-deployUnit 必须是 JSON 数组")
    return units


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="创建 Feature（create_feature）")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--selected-deployUnit", dest="units")
    parser.add_argument("--workflow-template", default="standard")
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    holder = {}

    def action():
        args = parser.parse_args(argv)
        project = query.resolve_project(args.workspace, args.project)
        feature = query.resolve_feature(args.feature)
        result = engine.init_feature(project, feature, owner=args.owner, iteration=args.iteration,
                                     template=args.workflow_template, deploy_units=parse_units(args.units))
        holder.update(project=project, feature=feature, seq=result.pop("boardSeq"))
        return result

    code = cli.run(action)
    if code == 0:
        board_events.push(holder["project"], holder["feature"], "create_feature", holder["seq"])
    return code


if __name__ == "__main__":
    sys.exit(main())
