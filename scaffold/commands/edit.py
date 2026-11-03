"""编辑核心配置的便捷命令：add node、add skill、module list/enable/disable（interfaces.md §1.1，D56）。

修改先在内存中完成（在原文上插入或替换片段，保留键序、缩进和换行），然后用叠加后的视图走 doctor 流水线，
没有 error 时与生成结果一起写盘，否则什么都不写。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scaffold.commands import CommandResult
from scaffold.commands.check import frontmatter_issues, legacy_refs
from scaffold.commands.doctor import doctor
from scaffold.build.load import ENTRY, MODULE_KEYS, rel_path
from scaffold.lib import derive, fsio, jsonedit, jsonschema, skillmd
from scaffold.lib.issues import UsageError, warning
from scaffold.lib.tree import Tree

SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKIPPED = ("__pycache__", ".DS_Store", "Thumbs.db", ".git")


def entry_of(tree: Tree) -> tuple:
    data = tree.read_bytes(ENTRY)
    if data is None:
        raise UsageError(f"找不到入口文件 {ENTRY}：{tree.path(ENTRY)}")
    try:
        entry = fsio.parse_json(data, ENTRY)
    except fsio.JsonError as error:
        raise UsageError(f"{ENTRY} 不是合法的 JSON：{error.describe()}") from None
    return fsio.decode(data), entry


def workflow_rel(entry: dict) -> str:
    return rel_path(entry.get("workflow", "./workflow.json"))


def bound_skills(tree: Tree) -> set:
    data = tree.read_bytes(workflow_rel(entry_of(tree)[1]) if tree.is_file(ENTRY) else "workflow.json")
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


# —— add node ——

def add_node(root: Path, *, node_id: str, name: str, skill: str, stage: str, seq: int, outputs: list,
             terminal: bool = False) -> CommandResult:
    """在 nodes.<stage> 中按 seq 插到组内对应位置，不改其他节点的 seq（Q12.2、Q12.6）。outputs 为 [(路径, 是否可选)]。"""
    if stage not in derive.GROUPS:
        raise UsageError("--stage 只能是 biz、dev 或 ops")
    if terminal and outputs:
        raise UsageError("--terminal 不能与 --output、--optional-output 同时使用：终态节点不能有输出")
    tree = Tree(root)
    _, entry = entry_of(tree)
    rel = workflow_rel(entry)
    data = tree.read_bytes(rel)
    if data is None:
        raise UsageError(f"找不到 {rel}")
    text = fsio.decode(data)
    workflow = fsio.parse_json(data, rel)
    node = {"id": node_id, "seq": seq, "name": name, "skill": skill}
    if outputs:
        node["outputs"] = [{"path": path, "optional": True} if optional else path for path, optional in outputs]
    if terminal:
        node["terminal"] = True
    group = (workflow.get("nodes") or {}).get(stage)
    if group is None:
        text = jsonedit.set_member(text, "/nodes", stage, [node])
    else:
        index = sum(1 for item in group if isinstance(item, dict) and item.get("seq", 0) < seq)
        text = jsonedit.insert_item(text, f"/nodes/{stage}", index, node)
    return doctor(root, overlay={rel: text.encode("utf-8")})


# —— module list / enable / disable ——

def _module_rel(entry: dict, module_id: str) -> str:
    ref = (entry.get("modules") or {}).get(module_id)
    return rel_path(ref) if ref else f"modules/{module_id}.json"


def module_list(root: Path) -> CommandResult:
    from scaffold.lib.issues import Report
    from scaffold.modules import discover

    tree = Tree(root)
    _, entry = entry_of(tree)
    referenced = entry.get("modules") or {}
    modules, lines = [], []
    for module_id, spec in discover().items():
        enabled = spec.core or module_id in referenced
        file = _module_rel(entry, module_id) if module_id in referenced else None
        modules.append({"id": module_id, "title": spec.title, "version": spec.version, "core": spec.core,
                        "enabled": enabled, "file": file})
        state = "始终启用" if spec.core else ("已启用" if enabled else "未启用")
        lines.append(f"{module_id:<13} {spec.version:<8} {state:<6} {spec.title}" + (f"（{file}）" if file else ""))
    return CommandResult(Report(), extra={"modules": modules}, text="\n".join(lines))


def _schema_at(module_id: str, path: list):
    root = jsonschema.load_schema(f"modules/{module_id}.schema.json")
    node = root
    for index, part in enumerate(path):
        node = jsonschema.resolve(node, root)
        properties = node.get("properties", {})
        if part not in properties:
            if node.get("additionalProperties") not in (None, False) and not properties:
                raise UsageError(f"{'.'.join(path[:index])} 是以路径或 id 为键的映射，不能用 --set 指定，请直接编辑文件")
            raise UsageError(f"modules/{module_id}.json 中没有 {'.'.join(path[:index + 1])}")
        node = properties[part]
    node = jsonschema.resolve(node, root)
    if node.get("type") == "object" and "additionalProperties" in node and not node.get("properties"):
        raise UsageError(f"{'.'.join(path)} 是以路径或 id 为键的映射，不能用 --set 指定，请直接编辑文件")
    return node


def parse_sets(module_id: str, sets: list) -> list:
    """--set key=value：key 沿 Schema 的属性用 . 逐级指定；value 按类型转换，字符串原样保留（Q12.7）。"""
    result = []
    for item in sets:
        if "=" not in item:
            raise UsageError(f"--set 要写成 key=value：{item}")
        key, raw = item.split("=", 1)
        path = [part for part in key.split(".") if part]
        if not path:
            raise UsageError(f"--set 缺少 key：{item}")
        schema = _schema_at(module_id, path)
        types = schema.get("type") if isinstance(schema.get("type"), list) else [schema.get("type")]
        if "string" in types or (schema.get("enum") and all(isinstance(value, str) for value in schema["enum"])) \
                or isinstance(schema.get("const"), str):
            value = raw
        else:
            try:
                value = json.loads(raw)
            except ValueError:
                raise UsageError(f"--set {key} 的值要写成 JSON：{raw}") from None
        result.append((path, value))
    return result


def _apply_sets(text: str, sets: list) -> str:
    for path, value in sets:
        current = fsio.parse_json(text)
        pointer = ""
        for part in path[:-1]:
            if not isinstance(current.get(part), dict):
                text = jsonedit.set_member(text, pointer, part, {})
                current = fsio.parse_json(text)
            current = current[part]
            pointer += "/" + part
        text = jsonedit.set_member(text, pointer, path[-1], value)
    return text


def _artifact_skeleton(tree: Tree, entry: dict) -> dict:
    data = tree.read_bytes(workflow_rel(entry))
    workflow = fsio.parse_json(data) if data else {"nodes": {}}
    paths = []
    for ref in derive.ordered_nodes(workflow):
        for item in ref.node.get("outputs", []):
            path, _ = derive.output_item(item)
            if not path.lower().endswith(".json") and path not in paths:
                paths.append(path)
    return {path: "[TODO: 简述]" for path in paths}


def module_enable(root: Path, module_id: str, sets: list) -> CommandResult:
    from scaffold.modules import discover

    if module_id not in MODULE_KEYS:
        raise UsageError(f"没有模块 {module_id}，可用：{'、'.join(MODULE_KEYS)}")
    if discover()[module_id].core:
        raise UsageError(f"{module_id} 是核心模块，始终启用；要修改它的配置请直接编辑 modules/{module_id}.json")
    tree = Tree(root)
    entry_text, entry = entry_of(tree)
    parsed = parse_sets(module_id, sets)
    rel = _module_rel(entry, module_id)
    overlay = {}
    data = tree.read_bytes(rel)
    if data is None:
        if module_id == "artifactSync" and not any(path[0] in ("allowedFrom", "allowedCheckpoints") for path, _ in parsed):
            raise UsageError("enable artifactSync 要用 --set 给出 allowedFrom 或 allowedCheckpoints，例如 --set allowedFrom=plan:done")
        skeleton = {"$schema": f"../.scaffold/modules/{module_id}.schema.json"}
        if module_id == "artifactSync":
            skeleton["artifacts"] = _artifact_skeleton(tree, entry)
        text = jsonedit.render(skeleton, "", "  ", "\n") + "\n"
    else:
        text = fsio.decode(data)
    text = _apply_sets(text, parsed)
    overlay[rel] = text.encode("utf-8")
    if module_id not in (entry.get("modules") or {}):
        if "modules" not in entry:
            entry_text = jsonedit.set_member(entry_text, "", "modules", {module_id: f"./{rel}"})
        else:
            entry_text = jsonedit.set_member(entry_text, "/modules", module_id, f"./{rel}")
        overlay[ENTRY] = entry_text.encode("utf-8")
    return doctor(root, overlay=overlay)


def module_disable(root: Path, module_id: str) -> CommandResult:
    """只去掉入口文件中的引用；modules/*.json 和模块以前生成的文件都保留，build-manifest 中标为 inactive（D52）。"""
    from scaffold.lib.issues import Report
    from scaffold.modules import discover

    if module_id not in MODULE_KEYS:
        raise UsageError(f"没有模块 {module_id}，可用：{'、'.join(MODULE_KEYS)}")
    if discover()[module_id].core:
        raise UsageError(f"{module_id} 是核心模块，不能关闭")
    tree = Tree(root)
    entry_text, entry = entry_of(tree)
    if module_id not in (entry.get("modules") or {}):
        return CommandResult(Report(), text=f"{module_id} 本来就没有启用")
    entry_text = jsonedit.remove_member(entry_text, "/modules", module_id)
    return doctor(root, overlay={ENTRY: entry_text.encode("utf-8")})
