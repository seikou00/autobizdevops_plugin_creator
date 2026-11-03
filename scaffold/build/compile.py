"""核心配置 → PluginIR（scaffold.md 单元 5）。前提：lint_core 没有 error。"""

from __future__ import annotations

from scaffold.build.ir import ArtifactIR, NodeIR, OutputRef, PluginIR
from scaffold.build.normalize import Normalized
from scaffold.lib import derive, skillmd


def derived_description(name: str, paths: list[str]) -> str:
    return f"{name}；产物：{'、'.join(paths)}" if paths else name


def skill_description(tree, skill_dir):
    if skill_dir is None:
        return None
    data = tree.read_bytes(f"{skill_dir}/SKILL.md")
    if data is None:
        return None
    return skillmd.description_of(skillmd.read_text(data))


def compile_ir(normalized: Normalized, skills: dict) -> PluginIR:
    tree = normalized.inputs.tree
    refs = derive.ordered_nodes(normalized.workflow)
    artifacts: dict = {}
    nodes = []
    for index, ref in enumerate(refs):
        node = ref.node
        outputs = []
        paths = []
        for item in node.get("outputs", []):
            path, required = derive.output_item(item)
            paths.append(path)
            artifact = derive.artifact_id(path)
            if artifact not in artifacts:
                artifacts[artifact] = ArtifactIR(artifact, path, (path,), derive.artifact_type(path), node["id"])
            outputs.append(OutputRef(artifact, required))
        found, _ = skills.get(node["skill"], (None, []))
        description = skill_description(tree, found)
        if skillmd.is_placeholder(description):
            description = derived_description(node["name"], paths)
        nodes.append(NodeIR(id=node["id"], name=node["name"], stage=derive.group_label(ref.group), seq=node["seq"],
                            order=(index + 1) * 10, skill=node["skill"], description=description,
                            terminal=bool(node.get("terminal", False)), outputs=tuple(outputs)))
    stages = tuple(derive.group_label(group) for group in derive.GROUPS
                   if normalized.workflow["nodes"].get(group))
    chain = tuple(checkpoint for node in nodes for checkpoint in node.checkpoints)
    return PluginIR(plugin=normalized.entry["plugin"], runtime=normalized.entry["runtime"], stages=stages,
                    nodes=tuple(nodes), artifacts=artifacts, checkpoint_chain=chain)
