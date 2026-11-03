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

    add = commands.add_parser("add", parents=[common], help="添加节点或技能")
    targets = add.add_subparsers(dest="target", parser_class=Parser)
    node = targets.add_parser("node", parents=[common], help="在 workflow.json 中添加节点")
    node.add_argument("node_id")
    node.add_argument("--name", required=True)
    node.add_argument("--skill", required=True)
    node.add_argument("--stage", required=True, choices=("biz", "dev", "ops"))
    node.add_argument("--seq", required=True, type=int)
    node.add_argument("--output", dest="outputs", action="append", default=[], type=lambda value: (value, False),
                      help="必需输出，可以重复；含 glob 的路径要加引号")
    node.add_argument("--optional-output", dest="outputs", action="append", type=lambda value: (value, True),
                      help="可选输出，可以重复")
    node.add_argument("--terminal", action="store_true", help="终态节点（只推进到 archived，不能有输出）")
    skill = targets.add_parser("skill", parents=[common], help="导入已有技能目录，或创建空白 SKILL.md")
    skill.add_argument("skill")
    skill.add_argument("--from", dest="source", help="已有技能目录")

    module = commands.add_parser("module", parents=[common], help="列出、启用或关闭模块")
    actions = module.add_subparsers(dest="action", parser_class=Parser)
    actions.add_parser("list", parents=[common], help="列出可用模块、版本及启用状态")
    enable = actions.add_parser("enable", parents=[common], help="启用 knowledge 或 artifactSync")
    enable.add_argument("module_id")
    enable.add_argument("--set", dest="sets", action="append", default=[], help="key=value，key 沿 Schema 用 . 逐级指定")
    disable = actions.add_parser("disable", parents=[common], help="关闭 knowledge 或 artifactSync（只去掉引用）")
    disable.add_argument("module_id")

    doctor = commands.add_parser("doctor", parents=[common], help="修改核心配置或更新脚手架后重新生成插件")
    doctor.add_argument("--dry-run", action="store_true", help="只列出将要发生的变化，不写文件")
    doctor.add_argument("--force", action="store_true", help="覆盖被手改过的托管文件")
    doctor.add_argument("--allow-id-change", action="store_true", help="确认修改 plugin.id")
    doctor.add_argument("--allow-layout-change", action="store_true", help="确认修改 runtime.metaRoot")
    doctor.add_argument("--allow-major-upgrade", action="store_true", help="确认运行框架跨主版本升级")

    for name, text in (("lint", "只检查核心配置"), ("check", "lint 加上技能内容、漂移检查和契约测试")):
        command = commands.add_parser(name, parents=[common], help=text)
        command.add_argument("--strict", action="store_true", help="warning 也视为 error")

    simulate = commands.add_parser("simulate", parents=[common], help="在临时目录中按宿主的方式调用一遍插件")
    simulate.add_argument("--feature", default="demo")
    simulate.add_argument("--to", help="停在这个 checkpoint")
    simulate.add_argument("--platform", choices=("darwin", "linux", "win32"), help="默认为当前平台")
    simulate.add_argument("--keep", action="store_true", help="保留临时目录便于排查")

    package = commands.add_parser("package", parents=[common], help="检查后打包成 zip")
    package.add_argument("-o", dest="output", help="zip 路径，默认为 dist/<plugin.id>-<plugin.version>.zip")
    return parser


def run(args) -> object:
    root = Path(getattr(args, "directory", "."))
    if args.command == "new":
        from scaffold.commands.new import load_answers, new

        return new(Path(args.target), template=args.template, answers=load_answers(args.answers), yes=args.yes)
    if args.command == "add":
        from scaffold.commands import edit

        if args.target == "node":
            return edit.add_node(root, node_id=args.node_id, name=args.name, skill=args.skill, stage=args.stage,
                                 seq=args.seq, outputs=args.outputs, terminal=args.terminal)
        if args.target == "skill":
            return edit.add_skill(root, args.skill, source=Path(args.source) if args.source else None)
        raise UsageError("用法：autobiz-plugin add node|skill …")
    if args.command == "module":
        from scaffold.commands import edit

        if args.action == "list":
            return edit.module_list(root)
        if args.action == "enable":
            return edit.module_enable(root, args.module_id, args.sets)
        if args.action == "disable":
            return edit.module_disable(root, args.module_id)
        raise UsageError("用法：autobiz-plugin module list|enable|disable …")
    if args.command == "doctor":
        from scaffold.commands.doctor import doctor

        allow = frozenset(name for name, flag in (("id-change", args.allow_id_change),
                                                  ("layout-change", args.allow_layout_change),
                                                  ("major-upgrade", args.allow_major_upgrade)) if flag)
        return doctor(root, dry_run=args.dry_run, force=args.force, allow=allow)
    if args.command == "lint":
        from scaffold.commands.lint import lint

        return lint(root)
    if args.command == "check":
        from scaffold.commands.check import check

        return check(root, strict=args.strict)
    if args.command == "simulate":
        from scaffold.commands.simulate import simulate

        return simulate(root, feature=args.feature, to=args.to, platform=args.platform, keep=args.keep)
    if args.command == "package":
        from scaffold.commands.package import package

        return package(root, output=Path(args.output) if args.output else None)
    raise UsageError("缺少子命令：new、add、module、doctor、lint、check、simulate、package")


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
