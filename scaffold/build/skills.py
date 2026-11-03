"""节点技能 SKILL.md 的状态维护片段同步（output-spec.md §6.1，scaffold.md 单元 7）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold.build.framework import skill_dir
from scaffold.lib import skillmd


@dataclass
class SkillChanges:
    created: list = field(default_factory=list)
    stateInserted: list = field(default_factory=list)
    stateUpdated: list = field(default_factory=list)
    stateRemoved: list = field(default_factory=list)

    def to_json(self) -> dict:
        return {"created": self.created, "stateInserted": self.stateInserted, "stateUpdated": self.stateUpdated,
                "stateRemoved": self.stateRemoved}


@dataclass(frozen=True)
class SkillFile:
    path: str
    data: bytes
    recorded: bool              # 节点技能记入 build-manifest（seeded）；被删掉片段的技能不再记录
    region: str | None = None   # 状态维护片段的摘要


def plan_skills(ir, tree, skill_dirs: dict, previous: dict | None):
    """返回 (SkillFile 列表, SkillChanges, 节点技能 SKILL.md 路径 → description)。"""
    files: list[SkillFile] = []
    changes = SkillChanges()
    descriptions: dict = {}
    bound = set()
    for node in ir.nodes:
        path = f"{skill_dir(skill_dirs, node.skill)}/SKILL.md"
        bound.add(path)
        block = skillmd.render_state_block(node.id, node.terminal)
        data = tree.read_bytes(path)
        if data is None:
            text = skillmd.blank_skill(node.skill, block)
            changes.created.append(path)
        else:
            original = skillmd.read_text(data)
            text = skillmd.upsert_state(original, block)
            if text != original:
                (changes.stateUpdated if skillmd.has_state(original) else changes.stateInserted).append(path)
        descriptions[path] = skillmd.description_of(text)
        files.append(SkillFile(path, text.encode("utf-8"), True, skillmd.state_digest(text)))
    for path, record in sorted((previous or {}).get("files", {}).items()):
        if record.get("ownership") != "seeded" or path in bound:
            continue
        data = tree.read_bytes(path)
        if data is None:
            continue
        original = skillmd.read_text(data)
        if skillmd.has_state(original):
            files.append(SkillFile(path, skillmd.remove_state(original).encode("utf-8"), False))
            changes.stateRemoved.append(path)
    return files, changes, descriptions
