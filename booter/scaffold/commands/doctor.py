"""doctor：修改核心配置或更新脚手架后重新生成插件——lint → 与上次构建比较并列出影响 → build → 复查（interfaces.md §1.7）。

脚手架更新后同一主版本内直接替换 managed、module 文件，changes.versions 列出版本变化（D57）。
"""

from __future__ import annotations

from scaffold.build import emit
from scaffold.build.manifest import MANIFEST
from scaffold.build.pipeline import analyze, build
from scaffold.commands import CommandResult
from scaffold.lib import fsio, skillmd
from scaffold.lib.issues import Report, error, warning
from scaffold.lib.tree import Tree

FLOW = "runtime/config/flow.json"


def previous_flow(tree: Tree):
    data = tree.read_bytes(FLOW)
    if data is None:
        return None
    try:
        value = fsio.parse_json(data, FLOW)
    except fsio.JsonError:
        return None
    return value if isinstance(value, dict) and isinstance(value.get("nodes"), list) else None


def diff(analysis, tree: Tree):
    """返回 (changes 的 inputs/nodes 部分, issues)。"""
    issues = []
    ir = analysis.ir
    previous = analysis.previous
    recorded = (previous or {}).get("inputs", {})
    inputs = [rel for rel, value in analysis.normalized.inputs.digests.items() if recorded.get(rel) != value]
    new_ids = [node.id for node in ir.nodes]
    if previous is None:
        return {"inputs": inputs, "nodes": {"added": new_ids, "removed": [], "reordered": False}}, issues
    flow = previous_flow(tree)
    if flow is None:
        issues.append(warning("DOCTOR_BASELINE_MISSING", f"{FLOW} 不存在或无法解析，本次没有影响报告，直接重新生成",
                              file=FLOW))
        return {"inputs": inputs, "nodes": {"added": [], "removed": [], "reordered": False}}, issues
    old_ids = [node.get("id") for node in flow["nodes"]]
    common_old = [node_id for node_id in old_ids if node_id in new_ids]
    common_new = [node_id for node_id in new_ids if node_id in old_ids]
    old_chain = flow.get("checkpoints", {}).get("chain", [])
    removed_checkpoints = [checkpoint for checkpoint in old_chain if checkpoint not in ir.checkpoint_chain]
    if removed_checkpoints:
        issues.append(warning("CHECKPOINT_REMOVED", f"上次构建的 {'、'.join(removed_checkpoints)} 在新流程中不存在",
                              file=analysis.normalized.inputs.files["workflow"],
                              hint="停在这些 checkpoint 上的已有 Feature 需要人工处理"))
    return {"inputs": inputs,
            "nodes": {"added": [node_id for node_id in new_ids if node_id not in old_ids],
                      "removed": [node_id for node_id in old_ids if node_id not in new_ids],
                      "reordered": common_old != common_new}}, issues


def recheck(tree: Tree, result) -> list:
    """生成后复查：不应再有 BUILD_STALE，各节点技能的片段与推导结果一致。"""
    issues = [issue for issue in analyze(tree, stale=True).report.issues if issue.code == "BUILD_STALE"]
    for node in result.ir.nodes:
        found, _ = result.skill_dirs.get(node.skill, (None, []))
        path = f"{found or f'skills/{node.skill}'}/SKILL.md"
        data = tree.read_bytes(path)
        expected = skillmd.block_digest(skillmd.render_state_block(node.id, node.terminal))
        if data is None or skillmd.state_digest(skillmd.read_text(data)) != expected:
            issues.append(error("SKILL_STATE_BLOCK", f"生成后节点 {node.id} 的状态维护片段仍不正确", file=path))
    return issues


def doctor(root, *, dry_run: bool = False, force: bool = False, allow: frozenset = frozenset(),
           overlay: dict | None = None, extra_issues=()) -> CommandResult:
    tree = Tree(root, overlay)
    report = Report(extra_issues)
    analysis = analyze(tree, stale=False, allow=allow)
    report.extend(analysis.report.issues)
    if report.failed():
        return CommandResult(report)
    changes, issues = diff(analysis, tree)
    report.extend(issues)
    result = build(tree, dry_run=True, force=force, allow=allow)
    report.extend(issue for issue in result.report.issues if issue not in report.issues)
    if result.report.failed():
        return CommandResult(report)
    changes["skills"] = result.skills.to_json()
    changes["versions"] = analysis.versions.to_json()
    extra = {"changes": changes}
    if dry_run:
        pending = emit.changed_files(result.plan, tree)
        return CommandResult(report, extra=extra, text=_summary(changes, pending, dry_run=True))
    written = []
    for rel, data in sorted((overlay or {}).items()):
        if not fsio.same_content(Tree(root).read_bytes(rel), data):
            fsio.atomic_write(tree.path(rel), data)
            written.append(rel)
    disk = Tree(root)
    written += [path for path in emit.apply(result.plan, disk, MANIFEST, fsio.dump_json(result.manifest))
                if path not in written]
    report.extend(recheck(disk, result))
    return CommandResult(report, extra=extra, written=written, text=_summary(changes, written))


def _summary(changes: dict, files: list, *, dry_run: bool = False) -> str:
    nodes = changes["nodes"]
    lines = []
    if changes["inputs"]:
        lines.append("改过的核心配置：" + "、".join(changes["inputs"]))
    if nodes["added"]:
        lines.append("新增节点：" + "、".join(nodes["added"]))
    if nodes["removed"]:
        lines.append("删除节点：" + "、".join(nodes["removed"]))
    if nodes["reordered"]:
        lines.append("节点顺序有变化")
    versions = changes.get("versions") or {}
    moved = [f"{key} {value['from']} → {value['to']}" for key, value in (("脚手架", versions.get("scaffold")),
                                                                          ("运行框架", versions.get("core"))) if value]
    moved += [f"模块 {key} {value['from']} → {value['to']}" for key, value in (versions.get("modules") or {}).items()]
    if moved:
        lines.append("版本变化：" + "、".join(moved))
    for key, label in (("created", "生成空白 SKILL.md"), ("stateInserted", "插入状态维护片段"),
                       ("stateUpdated", "更新状态维护片段"), ("stateRemoved", "删除状态维护片段")):
        if changes["skills"][key]:
            lines.append(f"{label}：" + "、".join(changes["skills"][key]))
    if files:
        lines.append(("将要写入" if dry_run else "已写入") + f" {len(files)} 个文件")
    else:
        lines.append("插件已是最新，没有文件需要写入")
    return "\n".join(lines)
