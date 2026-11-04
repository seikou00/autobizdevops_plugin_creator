"""节点技能按阶段放进分组目录（D64）：doctor 把不在 skills/autobiz|autodev|autoops/<技能>/ 的节点技能挪过去。

挪动整个技能目录，并把 skills/ 下开发者文件（不含脚手架生成、托管的文件）中对旧目录的引用改成新目录。
结果是一个 overlay（新路径 → 内容，旧路径 → None），由 doctor 与生成结果一起写盘，有 error 时什么都不写。
"""

from __future__ import annotations

import re

from scaffold.lib import fsio
from scaffold.lib.issues import error

OWNED = ("generated", "managed", "module")


def relocate(analysis, tree) -> tuple:
    """返回 (overlay, [(旧目录, 新目录)], issues)。analysis 是 pipeline.analyze 的结果。"""
    if analysis.normalized is None or not analysis.skill_dirs:
        return {}, [], []
    moves, issues = [], []
    for skill, (found, candidates, target) in sorted(analysis.skill_dirs.items()):
        if found is None or found == target or len(candidates) != 1:
            continue
        if tree.is_dir(target):
            issues.append(error("SKILL_LAYOUT_CONFLICT", f"技能 {skill} 要挪到 {target}/，但这个目录已经存在",
                                file=f"{found}/SKILL.md", hint=f"删掉或改名 {target}/ 后再执行 doctor"))
            continue
        moves.append((found, target))
    if not moves or issues:
        return {}, [], issues
    owned = {path for path, record in ((analysis.previous or {}).get("files") or {}).items()
             if record.get("ownership") in OWNED}
    patterns = [(re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(f"{old}/")), f"{new}/") for old, new in moves]
    overlay = {}
    for rel in tree.walk("skills"):
        data = tree.read_bytes(rel)
        if data is None:
            continue
        target = rel
        for old, new in moves:
            if rel.startswith(f"{old}/"):
                target = new + rel[len(old):]
        if rel not in owned and fsio.is_text(data):
            text = fsio.decode(data)
            rewritten = text
            for pattern, replacement in patterns:
                rewritten = pattern.sub(replacement, rewritten)
            if rewritten != text:
                data = rewritten.encode("utf-8")
        if target != rel:
            overlay[target] = data
            overlay[rel] = None
        elif data != tree.read_bytes(rel):
            overlay[rel] = data
    return overlay, moves, []
