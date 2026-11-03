"""add skill：导入已有技能目录或创建空白 SKILL.md，然后在内存中走 doctor 流水线，没有 error 时一起写盘（D56）。"""

from __future__ import annotations

import re
from pathlib import Path

from scaffold.commands import CommandResult
from scaffold.commands.check import frontmatter_issues, legacy_refs
from scaffold.commands.doctor import doctor
from scaffold.lib import fsio, skillmd
from scaffold.lib.issues import UsageError, warning
from scaffold.lib.tree import Tree

SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKIPPED = ("__pycache__", ".DS_Store", "Thumbs.db", ".git")


def bound_skills(tree: Tree) -> set:
    data = tree.read_bytes("workflow.json")
    if data is None:
        return set()
    try:
        workflow = fsio.parse_json(data)
    except fsio.JsonError:
        return set()
    return {node.get("skill") for group in (workflow.get("nodes") or {}).values() for node in group or []
            if isinstance(node, dict)}


def is_blank(tree: Tree, skill: str) -> bool:
    """skills/<skill>/ 下只有 build 生成的空白 SKILL.md（frontmatter 和状态维护片段，description 仍是占位）。"""
    if tree.walk(f"skills/{skill}") != [f"skills/{skill}/SKILL.md"]:
        return False
    text = skillmd.read_text(tree.read_bytes(f"skills/{skill}/SKILL.md"))
    front = skillmd.parse_frontmatter(text)
    body = skillmd.remove_state(text[front.body_start:])
    return skillmd.is_placeholder(front.fields.get("description")) and not body.strip()


def import_skill(tree: Tree, skill: str, source: Path | None, *, bound: bool) -> tuple:
    """返回 (overlay, issues, notes)：导入时发现的内容问题只报 warning，照样导入（Q12.5）。"""
    if len(skill) > 64 or not SKILL_NAME.match(skill):
        raise UsageError(f"技能名 {skill} 不合法：只能用小写字母、数字和连字符，不超过 64 字符")
    _, candidates = skillmd.find_skill_dir(tree, skill)
    replace_blank = candidates == [f"skills/{skill}"] and is_blank(tree, skill)
    if (tree.is_dir(f"skills/{skill}") or candidates) and not (replace_blank and source is not None):
        where = "、".join(candidates) or f"skills/{skill}"
        raise UsageError(f"技能 {skill} 已存在（{where}），不能重复导入")
    prefix = f"skills/{skill}"
    overlay, issues, notes = {}, [], []
    if source is None:
        overlay[f"{prefix}/SKILL.md"] = f"---\nname: {skill}\ndescription: {skillmd.TODO_DESCRIPTION}\n---\n".encode()
        return overlay, issues, notes
    source = Path(source).expanduser()
    if not (source / "SKILL.md").is_file():
        raise UsageError(f"{source} 下没有 SKILL.md")
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source).as_posix()
        if not path.is_file() or any(part in SKIPPED for part in rel.split("/")) or rel.endswith(".pyc"):
            continue
        overlay[f"{prefix}/{rel}"] = path.read_bytes()
    text = skillmd.read_text(overlay[f"{prefix}/SKILL.md"])
    text, renamed = skillmd.set_name(text, skill)
    if renamed:
        notes.append(f"frontmatter 的 name 已改为 {skill}")
    text, moved = skillmd.migrate_frontmatter(text)
    notes += moved
    overlay[f"{prefix}/SKILL.md"] = text.encode("utf-8")
    path = f"{prefix}/SKILL.md"
    for issue in frontmatter_issues(path, text) + legacy_refs(path, text, node_skill=bound, level="warning"):
        issues.append(warning(issue.code, issue.message, file=issue.file,
                              hint=(issue.hint + "；" if issue.hint else "") + "check 和 package 会把它报为 error"))
    return overlay, issues, notes


def add_skill(root: Path, skill: str, *, source: Path | None = None) -> CommandResult:
    tree = Tree(root)
    if not tree.is_file("plugin.scaffold.json"):
        raise UsageError(f"找不到入口文件 plugin.scaffold.json：{tree.path('plugin.scaffold.json')}")
    overlay, issues, notes = import_skill(tree, skill, source, bound=skill in bound_skills(tree))
    result = doctor(root, overlay=overlay, extra_issues=issues)
    if notes:
        result.text = "\n".join(notes + ([result.text] if result.text else []))
    return result
