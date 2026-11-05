"""check：lint 加上技能内容规则、生成文件漂移检查和契约测试，只读（input-config.md §7.3，D54、D55）。"""

from __future__ import annotations

import re
from pathlib import Path

from scaffold.build.framework import skill_dir
from scaffold.build.manifest import MANIFEST
from scaffold.build.pipeline import analyze, build
from scaffold.commands import CommandResult
from scaffold.lib import fsio, skillmd
from scaffold.lib.issues import Issue, Report, error, warning
from scaffold.lib.tree import Tree

NODE_STATE_COMMANDS = ("update_state.py", "update_checkpoint.py", "route_checkpoint.py")
LEGACY_PATHS = ("hooks/update_state.py", "hooks/update_checkpoint.py", "hooks/route_checkpoint.py", "hooks/skip_node.py",
                "hooks/init_workspace.py", "${pluginPath}/inspect_state.py")
LEGACY_HINT = ("状态由开头的状态维护片段维护，删掉这一行；整节只剩状态命令时连同小节标题一起删；"
               "这一行前面有校验等步骤时，改写成“执行完成命令之前先……”")
MAX_LINES = 500
TODO = "[TODO"


def all_skill_files(tree: Tree) -> list:
    """skills/<skill>/SKILL.md 和 skills/<分组>/<skill>/SKILL.md，以及分组目录自己的 SKILL.md。"""
    result = []
    for name in tree.list_dir("skills"):
        if tree.is_file(f"skills/{name}/SKILL.md"):
            result.append(f"skills/{name}/SKILL.md")
        if tree.is_dir(f"skills/{name}"):
            for child in tree.list_dir(f"skills/{name}"):
                if tree.is_file(f"skills/{name}/{child}/SKILL.md"):
                    result.append(f"skills/{name}/{child}/SKILL.md")
    return sorted(result)


def _section(lines: list, index: int) -> str:
    for line in reversed(lines[:index]):
        match = re.match(r"^#{1,6}\s+(.*)$", line)
        if match:
            return match.group(1).strip()
    return "（开头）"


def legacy_refs(path: str, text: str, *, node_skill: bool, level: str = "error") -> list:
    """跳过 frontmatter 和状态维护片段，逐行查找旧状态命令和旧入口路径（D51）。"""
    front = skillmd.parse_frontmatter(text)
    body = text[front.body_start:]
    offset = text[:front.body_start].count("\n")
    span = None
    if skillmd.has_state(body):
        begin = body.find(skillmd.STATE_BEGIN)
        end = body.find(skillmd.STATE_END, begin)
        span = (body[:begin].count("\n"), body[:end].count("\n"))
    lines = body.splitlines()
    issues = []
    needles = LEGACY_PATHS + (NODE_STATE_COMMANDS if node_skill else ())
    for index, line in enumerate(lines):
        if span and span[0] <= index <= span[1]:
            continue
        if any(needle in line for needle in needles):
            make = error if level == "error" else warning
            issues.append(make("LEGACY_ENTRY_REF",
                               f"第 {index + 1 + offset} 行（小节“{_section(lines, index)}”）：{line.strip()}",
                               file=path, hint=LEGACY_HINT))
    return issues


def frontmatter_issues(path: str, text: str) -> list:
    front = skillmd.parse_frontmatter(text)
    issues = []
    if not front.present:
        return [error("SKILL_FRONTMATTER", "缺少 frontmatter：宿主靠它加载技能", file=path,
                      hint="在文件开头写 ---、name、description、---")]
    for problem in front.errors:
        issues.append(error("SKILL_FRONTMATTER", problem, file=path,
                            hint="只支持单行 `键: 值` 和 metadata 下一层缩进的 `键: 值`（D45）"))
    for key in front.fields:
        if key not in skillmd.ALLOWED_KEYS:
            issues.append(error("SKILL_FRONTMATTER", f"frontmatter 不允许 {key} 键，只允许 " + "、".join(skillmd.ALLOWED_KEYS),
                                file=path, hint="版本号等自定义信息放进 metadata，例如 metadata.version"))
    description = front.fields.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(error("SKILL_FRONTMATTER", "description 必填", file=path))
    elif len(description) > 1024 or "<" in description or ">" in description:
        issues.append(error("SKILL_FRONTMATTER", "description 不能超过 1024 字符，也不能含 < >", file=path))
    return issues


def resource_rules(result, tree: Tree, *, package_mode: bool = False) -> list:
    issues = []
    ir = result.ir
    bound = {}
    for node in ir.nodes:
        bound[f"{skill_dir(result.skill_dirs, node.skill)}/SKILL.md"] = node
    module_skills = {path for path, record in (result.previous or {}).get("files", {}).items()
                     if record.get("ownership") == "module" and path.endswith("/SKILL.md")}
    for path in all_skill_files(tree):
        if path in module_skills:
            continue
        text = skillmd.read_text(tree.read_bytes(path))
        node = bound.get(path)
        issues += frontmatter_issues(path, text)
        if text.count("\n") + 1 > MAX_LINES:
            issues.append(warning("SKILL_TOO_LONG", f"SKILL.md 超过 {MAX_LINES} 行", file=path,
                                  hint="把细节拆到 references/，并在正文中写明什么时候读哪个文件"))
        issues += legacy_refs(path, text, node_skill=node is not None)
        if node is not None:
            name = skillmd.parse_frontmatter(text).fields.get("name")
            if name is not None and name != node.skill:
                issues.append(error("SKILL_NAME_MISMATCH", f"frontmatter 的 name 是 {name}，节点 {node.id} 绑定的技能是 {node.skill}",
                                    file=path, hint=f"把 name 改为 {node.skill}"))
            expected = skillmd.block_digest(skillmd.render_state_block(node.id, node.terminal))
            actual = skillmd.state_digest(text)
            if actual is None:
                issues.append(error("SKILL_STATE_BLOCK", f"缺少节点 {node.id} 的状态维护片段", file=path,
                                    hint="执行 autobiz-plugin doctor"))
            elif actual != expected:
                issues.append(error("SKILL_STATE_BLOCK", f"状态维护片段与节点 {node.id} 的推导结果不一致（被手改，或改了节点没有重新生成）",
                                    file=path, hint="执行 autobiz-plugin doctor"))
            if TODO in text:
                make = error if package_mode else warning
                issues.append(make("TODO_PLACEHOLDER", "还有未填写的 [TODO: …] 占位", file=path,
                                   hint="填写 description 和正文后再打包"))
        elif skillmd.has_state(text):
            issues.append(error("SKILL_STATE_BLOCK", "技能不再绑定任何节点，但还留着状态维护片段", file=path,
                                hint="执行 autobiz-plugin doctor，或手动删掉这个片段"))
    for key, rel in result.normalized.inputs.files.items():
        data = tree.read_bytes(rel)
        if data is not None and TODO.encode() in data:
            make = error if package_mode else warning
            issues.append(make("TODO_PLACEHOLDER", "还有未填写的 [TODO: …] 占位", file=rel))
    return issues


def drift_issues(tree: Tree, previous: dict | None, replaceable: set) -> list:
    issues = []
    for path, record in sorted((previous or {}).get("files", {}).items()):
        ownership = record.get("ownership")
        if record.get("inactive") or ownership not in ("generated", "managed", "module") or path in replaceable:
            continue
        data = tree.read_bytes(path)
        code = "DRIFT_GENERATED" if ownership == "generated" else "DRIFT_MANAGED"
        if data is None:
            issues.append(error(code, f"{path} 被删除了", file=path, hint="执行 autobiz-plugin doctor 重新生成"))
        elif fsio.digest(data) != record.get("sha256"):
            hint = ("这是生成文件，改核心配置后执行 autobiz-plugin doctor" if ownership == "generated"
                    else "不要手改托管文件；确认要覆盖时执行 autobiz-plugin doctor --force")
            issues.append(error(code, f"{path} 与上次生成时的内容不同，被手改过", file=path, hint=hint))
    return issues


def check(root: Path, *, strict: bool = False, package_mode: bool = False) -> CommandResult:
    from scaffold.commands.simulate import run_contract

    tree = Tree(root)
    result = analyze(tree, stale=True)
    report = Report(Issue("error", issue.code, issue.message, issue.file, issue.pointer, issue.hint)
                    if issue.code == "SKILL_MISSING" else issue for issue in result.report.issues)
    extra = {}
    if result.ir is not None and not any(issue.level == "error" and issue.code != "BUILD_STALE"
                                         for issue in report.issues):
        if result.previous is None:
            report.add("error", "BUILD_STALE", "插件还没有生成过：缺少 runtime/build-manifest.json", file=MANIFEST,
                       hint="执行 autobiz-plugin doctor")
        else:
            report.extend(resource_rules(result, tree, package_mode=package_mode))
            replay = build(tree, dry_run=True)
            replaceable = {path for path, planned in (replay.plan.files.items() if replay.plan else [])
                           if planned.replaceable}
            report.extend(drift_issues(tree, result.previous, replaceable))
            for module_id, module in result.modules.items():
                report.extend(module.prepare(tree.root, result.normalized.modules[module_id], install=False))
    if report.failed():
        extra["contract"] = {"ran": False, "reason": "lint 或漂移检查有 error，磁盘上的插件已经不对应当前配置"}
    else:
        simulation, issues = run_contract(root)
        report.extend(issues)
        extra["contract"] = simulation
    return CommandResult(report, extra=extra)
