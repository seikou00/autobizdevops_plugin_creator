"""核心配置的语义规则（input-config.md §7.2，scaffold.md 单元 4，D47）。

lint 分两段：先跑核心规则，没有 error 时再 compile 并跑各模块的 validate。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from scaffold.build.manifest import current_descriptions, recorded_inputs, stale_inputs
from scaffold.build.normalize import Normalized
from scaffold.lib import derive
from scaffold.lib.issues import Issue, error, warning
from scaffold.lib.skillmd import find_skill_dir

ENTRY = "plugin.scaffold.json"


@dataclass(frozen=True)
class LintContext:
    normalized: Normalized
    previous: dict | None
    skills: dict                                  # 节点技能 → (找到的目录, 候选, 应在的分组目录)
    allow: frozenset = field(default_factory=frozenset)

    @property
    def workflow_file(self) -> str:
        return self.normalized.inputs.files["workflow"]

    @property
    def tree(self):
        return self.normalized.inputs.tree


def skill_dirs(normalized: Normalized) -> dict:
    """节点技能 → (唯一找到的目录或 None, 全部候选, 应在的分组目录)。"""
    tree = normalized.inputs.tree
    return {ref.node["skill"]: (*find_skill_dir(tree, ref.node["skill"]), derive.skill_target(ref.group, ref.node["skill"]))
            for ref in derive.grouped_nodes(normalized.workflow)}


def _node_dup(ctx):
    seen = {}
    for ref in derive.grouped_nodes(ctx.normalized.workflow):
        node_id = ref.node["id"]
        if node_id in seen:
            yield error("NODE_DUP", f"节点 id {node_id} 重复（与 {seen[node_id]} 相同），推导出的 checkpoint 会重复",
                        file=ctx.workflow_file, pointer=f"{ref.pointer}/id", hint="各分组的节点 id 合起来不能重复")
        else:
            seen[node_id] = ref.pointer


def _seq_dup(ctx):
    seen = {}
    for ref in derive.grouped_nodes(ctx.normalized.workflow):
        seq = ref.node["seq"]
        if seq in seen:
            yield error("SEQ_DUP", f"节点 {ref.node['id']} 的 seq {seq} 与节点 {seen[seq]} 相同，无法确定先后",
                        file=ctx.workflow_file, pointer=f"{ref.pointer}/seq", hint="seq 可以跳号，但不能重复")
        else:
            seen[seq] = ref.node["id"]


def _seq_stage_order(ctx):
    refs = derive.grouped_nodes(ctx.normalized.workflow)
    for ref in refs:
        earlier = derive.GROUPS[:derive.GROUPS.index(ref.group)]
        for other in refs:
            if other.group in earlier and other.node["seq"] > ref.node["seq"]:
                yield error("SEQ_STAGE_ORDER",
                            f"{ref.group} 节点 {ref.node['id']} 的 seq {ref.node['seq']} 小于 {other.group} 节点 "
                            f"{other.node['id']} 的 seq {other.node['seq']}",
                            file=ctx.workflow_file, pointer=f"{ref.pointer}/seq",
                            hint="seq 要按 biz → dev → ops 递增")
                break


def _terminal_invalid(ctx):
    refs = derive.ordered_nodes(ctx.normalized.workflow)
    terminals = [ref for ref in refs if ref.node.get("terminal")]
    for ref in terminals:
        if ref.node.get("outputs"):
            yield error("TERMINAL_INVALID", f"终态节点 {ref.node['id']} 不能写 outputs", file=ctx.workflow_file,
                        pointer=f"{ref.pointer}/outputs")
        if ref is not refs[-1]:
            yield error("TERMINAL_INVALID", f"终态节点 {ref.node['id']} 必须是 seq 最大的节点", file=ctx.workflow_file,
                        pointer=f"{ref.pointer}/terminal")
    for ref in terminals[1:]:
        yield error("TERMINAL_INVALID", f"终态节点最多一个，{ref.node['id']} 是多出来的", file=ctx.workflow_file,
                    pointer=f"{ref.pointer}/terminal")


def _skill_shared(ctx):
    owners = {}
    for ref in derive.grouped_nodes(ctx.normalized.workflow):
        skill = ref.node["skill"]
        if skill in owners:
            yield error("SKILL_SHARED", f"技能 {skill} 同时绑定了节点 {owners[skill]} 和 {ref.node['id']}",
                        file=ctx.workflow_file, pointer=f"{ref.pointer}/skill",
                        hint="一份 SKILL.md 只能写一个节点的状态维护片段，每个节点用自己的技能")
        else:
            owners[skill] = ref.node["id"]


def _outputs(ctx):
    workflow = ctx.normalized.workflow
    ids = {}
    paths = {}
    for ref in derive.ordered_nodes(workflow):
        for index, item in enumerate(ref.node.get("outputs", [])):
            path, _ = derive.output_item(item)
            pointer = f"{ref.pointer}/outputs/{index}"
            reason = derive.unsafe_path(path)
            if reason:
                yield error("PATH_UNSAFE", f"产物路径 {path} {reason}", file=ctx.workflow_file, pointer=pointer)
            if path in paths:
                yield warning("OUTPUT_REDECLARED", f"{path} 已由节点 {paths[path]} 输出，视为同一个产物，以 {paths[path]} 为生产者",
                              file=ctx.workflow_file, pointer=pointer)
                continue
            paths[path] = ref.node["id"]
            artifact = derive.artifact_id(path)
            if not derive.ID_PATTERN.match(artifact):
                yield error("ARTIFACT_ID_INVALID", f"从 {path} 推导出的产物 id {artifact!r} 不符合 ^[a-z][a-z0-9_]*$",
                            file=ctx.workflow_file, pointer=pointer,
                            hint="产物 id 取路径中最后一个不含 glob 的段，改一下文件名或目录名")
            elif artifact in ids and ids[artifact][0] != path:
                yield error("ARTIFACT_ID_CONFLICT",
                            f"节点 {ref.node['id']} 的输出 {path} 与节点 {ids[artifact][1]} 的输出 {ids[artifact][0]} "
                            f"推导出同一个产物 id {artifact}",
                            file=ctx.workflow_file, pointer=pointer, hint="修改其中一个文件名，让两者推导出不同的产物 id")
            else:
                ids[artifact] = (path, ref.node["id"])


def _skills(ctx):
    for ref in derive.grouped_nodes(ctx.normalized.workflow):
        skill = ref.node["skill"]
        found, candidates, target = ctx.skills.get(skill, (None, [], derive.skill_target(ref.group, skill)))
        if len(candidates) > 1:
            yield error("SKILL_AMBIGUOUS", f"技能 {skill} 出现在多处：" + "、".join(candidates),
                        file=ctx.workflow_file, pointer=f"{ref.pointer}/skill", hint="只保留一个同名技能目录")
        elif found is None:
            yield warning("SKILL_MISSING", f"skills/{skill}/SKILL.md 和 skills/*/{skill}/SKILL.md 都不存在",
                          file=ctx.workflow_file, pointer=f"{ref.pointer}/skill",
                          hint=f"doctor 会在 {target}/ 生成空白 SKILL.md，由你填写正文")
        elif found != target:
            yield warning("SKILL_LAYOUT", f"技能 {skill} 在 {found}/，节点属于 {ref.group} 阶段，应在 {target}/",
                          file=ctx.workflow_file, pointer=f"{ref.pointer}/skill",
                          hint="doctor 会把整个技能目录挪过去，并改掉 skills/ 下文件中对旧路径的引用")


def _identity(ctx):
    previous = ctx.previous
    if previous is None:
        return
    entry = ctx.normalized.entry
    plugin_id = entry["plugin"]["id"]
    if previous.get("pluginId") not in (None, plugin_id):
        if "id-change" in ctx.allow:
            yield warning("PLUGIN_ID_CHANGED", f"已按新 ID {plugin_id} 重新生成；已有项目的 state.json 记录的仍是旧 ID "
                                               f"{previous['pluginId']}，会被拒绝读写，需要人工处理",
                          file=ENTRY, pointer="/plugin/id")
        else:
            yield error("PLUGIN_ID_CHANGED", f"plugin.id 从 {previous['pluginId']} 改成了 {plugin_id}，用过旧 ID 的项目会找不到状态",
                        file=ENTRY, pointer="/plugin/id", hint="确认要改时执行 autobiz-plugin doctor --allow-id-change")
    meta_root = entry["runtime"]["metaRoot"]
    if previous.get("metaRoot") not in (None, meta_root):
        if "layout-change" in ctx.allow:
            yield warning("LAYOUT_CHANGED", f"已按新的 metaRoot {meta_root} 重新生成；已有项目在 {previous['metaRoot']} 下的状态和产物"
                                            "需要人工迁移", file=ENTRY, pointer="/runtime/metaRoot")
        else:
            yield error("LAYOUT_CHANGED", f"runtime.metaRoot 从 {previous['metaRoot']} 改成了 {meta_root}，已有项目的状态会找不到",
                        file=ENTRY, pointer="/runtime/metaRoot",
                        hint="确认要改时执行 autobiz-plugin doctor --allow-layout-change")


def _plugin_refs(ctx):
    plugin = ctx.normalized.entry["plugin"]
    for key in ("mcpServers",):        # plugin.hooks 固定为 hooks/hooks.json，由 build 维护（load 检查）
        ref = plugin.get(key)
        if ref is None:
            continue
        rel = ref[2:] if ref.startswith("./") else ref
        if not ctx.tree.is_file(rel):
            yield error("PLUGIN_REF_MISSING", f"plugin.{key} 引用的 {rel} 不存在", file=ENTRY, pointer=f"/plugin/{key}",
                        hint="创建这个文件，或去掉这个字段")


def _inactive(ctx):
    files = [path for path, record in sorted((ctx.previous or {}).get("files", {}).items())
             if record.get("inactive") and ctx.tree.is_file(path)]
    if files:
        yield warning("MODULE_INACTIVE_FILES", "以下文件来自已关闭的模块或全局钩子，不再生效、不会打包，可以删除：" + "、".join(files),
                      file="runtime/build-manifest.json")


RULES = {
    "NODE_DUP": _node_dup,
    "SEQ_DUP": _seq_dup,
    "SEQ_STAGE_ORDER": _seq_stage_order,
    "TERMINAL_INVALID": _terminal_invalid,
    "SKILL_SHARED": _skill_shared,
    "OUTPUTS": _outputs,                  # PATH_UNSAFE、OUTPUT_REDECLARED、ARTIFACT_ID_INVALID、ARTIFACT_ID_CONFLICT
    "SKILLS": _skills,                    # SKILL_MISSING、SKILL_AMBIGUOUS
    "IDENTITY": _identity,                # PLUGIN_ID_CHANGED、LAYOUT_CHANGED
    "PLUGIN_REF_MISSING": _plugin_refs,
    "MODULE_INACTIVE_FILES": _inactive,
}


def build_stale(ctx) -> list[Issue]:
    if ctx.previous is None:
        return []
    descriptions = current_descriptions(ctx.tree, [ref.node for ref in derive.grouped_nodes(ctx.normalized.workflow)],
                                        ctx.skills)
    changed = stale_inputs(recorded_inputs(ctx.normalized.inputs, descriptions), ctx.previous)
    if not changed:
        return []
    return [error("BUILD_STALE", "改了以下内容但没有重新生成插件：" + "、".join(changed),
                  file=changed[0].split("#", 1)[0], hint="执行 autobiz-plugin doctor")]


def lint_core(ctx: LintContext, *, stale: bool = True) -> list[Issue]:
    issues = []
    for rule in RULES.values():
        issues.extend(rule(ctx))
    if stale:
        issues.extend(build_stale(ctx))
    return issues


def lint_modules(ir, normalized: Normalized, modules: dict, contexts: dict) -> list[Issue]:
    issues = []
    for module_id, module in modules.items():
        issues.extend(module.validate(ir, normalized.modules[module_id], contexts[module_id]))
    return issues


def group_by_code(issues):
    result = defaultdict(list)
    for issue in issues:
        result[issue.code].append(issue)
    return result
