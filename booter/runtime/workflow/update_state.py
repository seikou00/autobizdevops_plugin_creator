"""状态变更入口：技能开始时推进到 _in_progress，完成时推进到 _done（interfaces.md §4.2）。

重开等例外操作由人执行：--reopen 加非空的 --reason。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.adapters import board_events  # noqa: E402
from runtime.common import cli, engine, query  # noqa: E402


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="推进节点状态")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--feature")
    parser.add_argument("--workspace")
    parser.add_argument("--project")
    parser.add_argument("--reopen", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    parser.add_argument("--dry-run", action="store_true")
    holder = {}

    def action():
        args = parser.parse_args(argv)
        if args.project and not args.workspace:
            raise query.BoardError("--project 只能与 --workspace 一起使用")
        project = query.resolve_project(args.workspace, args.project)
        feature = query.resolve_feature(args.feature)
        result = engine.transition(project, feature, args.checkpoint, reopen=args.reopen, reason=args.reason,
                                   dry_run=args.dry_run, owner=args.owner, iteration=args.iteration)
        holder.update(project=project, feature=feature, seq=result.pop("boardSeq", None))
        return result

    code = cli.run(action)
    if code == 0:
        board_events.push(holder["project"], holder["feature"], "update_state", holder["seq"])
    return code


if __name__ == "__main__":
    sys.exit(main())
