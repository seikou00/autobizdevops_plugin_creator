"""命令行入口 autobiz-plugin（interfaces.md §1.1–§1.3）。

退出码：0 成功（可能带 warning）；1 存在 error 级问题，没有写入任何文件；2 用法错误。
所有命令都支持 -C <plugin-dir> 和 --json；stdout、stderr 固定为 UTF-8（D42）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scaffold import SCAFFOLD_VERSION
from scaffold.lib.issues import Report, UsageError, error


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _common() -> argparse.ArgumentParser:
    common = Parser(add_help=False)
    common.add_argument("-C", dest="directory", default=argparse.SUPPRESS, help="插件目录，默认为当前目录")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="输出机器可读的 JSON")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = Parser(prog="autobiz-plugin", description="AutoBiz 看板插件脚手架", parents=[common])
    parser.add_argument("--version", action="version", version=f"autobiz-plugin {SCAFFOLD_VERSION}")
    commands = parser.add_subparsers(dest="command", parser_class=Parser)

    new = commands.add_parser("new", parents=[common], help="以样例或回答为起点新建插件，随后执行 doctor")
    new.add_argument("target", help="插件目录，必须不存在或为空")
    new.add_argument("--from", dest="template", default="blank", choices=("blank", "lite", "fullstack"))
    new.add_argument("--answers", help="回答的 JSON 文件，- 表示从 stdin 读取")
    new.add_argument("--yes", action="store_true", help="不提问，回答取自 --from 的样例和 --answers")

    add = commands.add_parser("add", parents=[common], help="添加技能")
    targets = add.add_subparsers(dest="target", parser_class=Parser)
    skill = targets.add_parser("skill", parents=[common], help="导入已有技能目录，或创建空白 SKILL.md")
    skill.add_argument("skill")
    skill.add_argument("--from", dest="source", help="已有技能目录")

    doctor = commands.add_parser("doctor", parents=[common], help="修改核心配置或更新脚手架后重新生成插件")
    doctor.add_argument("--dry-run", action="store_true", help="只列出将要发生的变化，不写文件")
    doctor.add_argument("--force", action="store_true", help="覆盖被手改过的托管文件")
    doctor.add_argument("--allow-id-change", action="store_true", help="确认修改 plugin.id")
    doctor.add_argument("--allow-layout-change", action="store_true", help="确认修改 runtime.metaRoot")

    for name, text in (("lint", "只检查核心配置"), ("check", "lint 加上技能内容、漂移检查和契约测试")):
        command = commands.add_parser(name, parents=[common], help=text)
        command.add_argument("--strict", action="store_true", help="warning 也视为 error")

    package = commands.add_parser("package", parents=[common], help="检查后打包成 zip")
    package.add_argument("-o", dest="output", help="zip 路径，默认为 dist/<plugin.id>-<plugin.version>.zip")
    return parser


def run(args) -> object:
    root = Path(getattr(args, "directory", "."))
    if args.command == "new":
        from scaffold.commands.new import load_answers, new

        return new(Path(args.target), template=args.template, answers=load_answers(args.answers), yes=args.yes)
    if args.command == "add":
        if args.target != "skill":
            raise UsageError("用法：autobiz-plugin add skill <skill> [--from <dir>]")
        from scaffold.commands.edit import add_skill

        return add_skill(root, args.skill, source=Path(args.source) if args.source else None)
    if args.command == "doctor":
        from scaffold.commands.doctor import doctor

        allow = frozenset(name for name, flag in (("id-change", args.allow_id_change),
                                                  ("layout-change", args.allow_layout_change)) if flag)
        return doctor(root, dry_run=args.dry_run, force=args.force, allow=allow)
    if args.command == "lint":
        from scaffold.commands.lint import lint

        return lint(root)
    if args.command == "check":
        from scaffold.commands.check import check

        return check(root, strict=args.strict)
    if args.command == "package":
        from scaffold.commands.package import package

        return package(root, output=Path(args.output) if args.output else None)
    raise UsageError("缺少子命令：new、add skill、doctor、lint、check、package")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _emit(payload: dict, *, as_json: bool, text: str = "", report: Report | None = None) -> None:
    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return
    lines = [report.to_text()] if report is not None and report.issues else []
    if text:
        lines.append(text)
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    _configure_stdio()
    as_json = "--json" in (sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(argv)
        result = run(args)
    except UsageError as problem:
        report = Report([error("USAGE", str(problem))])
        _emit(report.to_json(), as_json=as_json, report=report)
        return 2
    strict = getattr(args, "strict", False)
    payload = result.report.to_json(written=result.written, strict=strict, **result.extra)
    _emit(payload, as_json=as_json, text=result.text, report=result.report)
    return 1 if result.report.failed(strict=strict) else 0


if __name__ == "__main__":
    sys.exit(main())
