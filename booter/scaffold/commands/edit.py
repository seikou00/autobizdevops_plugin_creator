"""编辑核心配置的便捷命令：add node、add skill(s)、module list/enable/disable（interfaces.md §1.1，D56）。

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
from scaffold.build.manifest import read_manifest
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


def is_blank(tree: Tree, directory: str) -> bool:
    """技能目录下只有 build 生成的空白 SKILL.md（frontmatter 和状态维护片段，description 仍是占位）。"""
    if tree.walk(directory) != [f"{directory}/SKILL.md"]:
        return False
    text = skillmd.read_text(tree.read_bytes(f"{directory}/SKILL.md"))
    front = skillmd.parse_frontmatter(text)
    body = skillmd.remove_state(text[front.body_start:])
    return skillmd.is_placeholder(front.fields.get("description")) and not body.strip()


def source_files(source: Path) -> list:
    """来源目录下要拷贝的文件 (相对路径, 内容)，跳过缓存和系统文件。"""
    files = []
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source).as_posix()
        if not path.is_file() or any(part in SKIPPED for part in rel.split("/")) or rel.endswith(".pyc"):
            continue
        files.append((rel, path.read_bytes()))
    return files


def import_agents(tree: Tree, source: Path) -> dict:
    """把 agents 目录原样拷到插件的 agents/：已有同名文件内容相同时跳过，不同时拒绝导入。"""
    source = Path(source).expanduser()
    if not source.is_dir():
        raise UsageError(f"agents 目录不存在：{source}")
    files = source_files(source)
    if not files:
        raise UsageError(f"agents 目录 {source} 中没有文件")
    overlay = {}
    for rel, data in files:
        target = f"agents/{rel}"
        existing = tree.read_bytes(target)
        if existing is None:
            overlay[target] = data
        elif not fsio.same_content(existing, data):
            raise UsageError(f"{target} 已存在且内容不同，不能覆盖")
    return overlay


def import_skill(tree: Tree, skill: str, source: Path | None, *, bound: bool, prefix: str | None = None) -> tuple:
    """返回 (overlay, issues, notes)：导入时发现的内容问题只报 warning，照样导入（Q12.5）。

    prefix 是导入到的目录，分组技能为 skills/<分组>/<skill>；不指定时导入到 build 生成的空白 SKILL.md 所在的
    目录（替换它），没有空白技能时导入到 skills/<skill>，doctor 再按节点阶段挪进分组目录（D64）。
    空白技能不在 prefix 时，overlay 中把它标为删除（None）。
    """
    if len(skill) > 64 or not SKILL_NAME.match(skill):
        raise UsageError(f"技能名 {skill} 不合法：只能用小写字母、数字和连字符，不超过 64 字符")
    _, candidates = skillmd.find_skill_dir(tree, skill)
    blanks = [candidate for candidate in candidates if is_blank(tree, candidate)] if source is not None else []
    blockers = [candidate for candidate in candidates if candidate not in blanks]
    prefix = prefix or (blanks[0] if blanks else f"skills/{skill}")
    if blockers or (tree.is_dir(prefix) and prefix not in blanks):
        where = "、".join(blockers or [prefix])
        raise UsageError(f"技能 {skill} 已存在（{where}），不能重复导入")
    overlay, issues, notes = {}, [], []
    if source is None:
        overlay[f"{prefix}/SKILL.md"] = f"---\nname: {skill}\ndescription: {skillmd.TODO_DESCRIPTION}\n---\n".encode()
        return overlay, issues, notes
    source = Path(source).expanduser()
    if not (source / "SKILL.md").is_file():
        raise UsageError(f"{source} 下没有 SKILL.md")
    for blank in blanks:
        if blank != prefix:
            overlay[f"{blank}/SKILL.md"] = None
            notes.append(f"已删除 build 生成的空白 {blank}/SKILL.md")
    for rel, data in source_files(source):
        overlay[f"{prefix}/{rel}"] = data
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


def _is_skill_dir(path: Path) -> bool:
    return path.is_dir() and path.name not in SKIPPED and (path / "SKILL.md").is_file()


def scan_collection(source: Path) -> tuple:
    """按插件 skills/ 的布局解析技能集合目录，返回 (技能 [(名字, 来源, 目标目录)], 资源 [(skills/ 下的路径, 内容)])。

    一级子目录本身含 SKILL.md、且它的子目录都不含 SKILL.md 时是技能；它的子目录中有含 SKILL.md 的，
    这个一级子目录是分组，这些子目录是分组下的技能（与 build 查找技能的两层一致，input-config.md §7.3）。
    其余内容（集合根目录和分组目录自己的 SKILL.md、references/、hooks/ 等）都是共享资源，按原路径拷入。
    技能目录内部更深层的 SKILL.md 属于技能自己的资源，随技能一起拷贝。
    来源目录自己含 SKILL.md、有技能子目录，且没有同样带 SKILL.md 的分组子目录时，它本身就是一个分组
    （例如 skills/autodev，其中 hooks/ 下的技能是分组资源），按分组导入。
    """
    children = [path for path in sorted(source.iterdir(), key=lambda path: path.name) if path.name not in SKIPPED]
    has_group = any(_is_skill_dir(child) and any(_is_skill_dir(path) for path in child.iterdir())
                    for child in children)
    if (source / "SKILL.md").is_file() and not has_group and any(_is_skill_dir(child) for child in children):
        names = {child.name for child in children if _is_skill_dir(child)}
        skills = [(name, source / name, f"skills/{source.name}/{name}") for name in sorted(names)]
        resources = [(f"skills/{source.name}/{rel}", data) for rel, data in source_files(source)
                     if rel.split("/")[0] not in names]
        return skills, resources
    skills, resources = [], []
    for child in children:
        if child.is_file():
            resources.append((f"skills/{child.name}", child.read_bytes()))
            continue
        nested = [path for path in sorted(child.iterdir(), key=lambda path: path.name) if _is_skill_dir(path)]
        if nested:
            skills += [(path.name, path, f"skills/{child.name}/{path.name}") for path in nested]
            names = {path.name for path in nested}
            resources += [(f"skills/{child.name}/{rel}", data) for rel, data in source_files(child)
                          if rel.split("/")[0] not in names]
        elif _is_skill_dir(child):
            skills.append((child.name, child, f"skills/{child.name}"))
        else:
            resources += [(f"skills/{child.name}/{rel}", data) for rel, data in source_files(child)]
    return skills, resources


def owned_paths(tree: Tree) -> set:
    """上次构建登记为脚手架所有（managed、module、generated）的文件。"""
    manifest = read_manifest(tree) or {}
    return {path for path, entry in (manifest.get("files") or {}).items()
            if isinstance(entry, dict) and entry.get("ownership") in ("managed", "module", "generated")}


def add_skills(root: Path, *, source: Path, agents: Path | None = None) -> CommandResult:
    """导入技能集合目录中的全部技能（支持一层分组）和共享资源，给了 agents 目录时一并拷到 agents/，
    整批只运行一次 doctor。"""
    tree = Tree(root)
    if not tree.is_file("plugin.scaffold.json"):
        raise UsageError(f"找不到入口文件 plugin.scaffold.json：{tree.path('plugin.scaffold.json')}")
    source = Path(source).expanduser()
    if not source.is_dir():
        raise UsageError(f"技能集合目录不存在：{source}")
    found, resources = scan_collection(source)
    if not found:
        raise UsageError(f"{source} 中没有找到含 SKILL.md 的技能（只查一级子目录和其下的分组）")
    seen = {}
    for skill, _, prefix in found:
        if skill in seen:
            raise UsageError(f"技能 {skill} 在集合中出现了两次（{seen[skill]}、{prefix}），build 无法确定用哪一个")
        seen[skill] = prefix

    owned = owned_paths(tree)
    bound = bound_skills(tree)
    overlay, issues, notes, names, skipped = {}, [], [], [], []
    for skill, skill_source, prefix in found:
        if any(path.startswith(prefix + "/") for path in owned):
            skipped.append(skill)
            continue
        imported, skill_issues, skill_notes = import_skill(tree, skill, skill_source, bound=skill in bound,
                                                           prefix=prefix)
        overlay.update(imported)
        issues.extend(skill_issues)
        notes.extend(f"{skill}：{note}" for note in skill_notes)
        names.append(skill)
    shared = 0
    for rel, data in resources:
        if rel in owned or any(rel.startswith(f"skills/{skill}/") for skill in skipped):
            continue
        if rel.endswith("/SKILL.md"):
            # 分组和集合根目录自己的 SKILL.md 也按技能文件检查，同样迁移 frontmatter
            text, moved = skillmd.migrate_frontmatter(skillmd.read_text(data))
            data = text.encode("utf-8")
            notes.extend(f"{rel}：{note}" for note in moved)
        existing = tree.read_bytes(rel)
        if existing is None:
            overlay[rel] = data
            shared += 1
        elif not fsio.same_content(existing, data):
            raise UsageError(f"{rel} 已存在且内容不同，不能覆盖")
    agent_files = import_agents(tree, agents) if agents is not None else {}
    overlay.update(agent_files)

    result = doctor(root, overlay=overlay, extra_issues=issues)
    if not result.report.failed():
        result.extra["importedSkills"] = names
        summary = [f"已导入 {len(names)} 个技能：{'、'.join(seen[name][len('skills/'):] for name in names)}"]
        if skipped:
            summary.append(f"跳过由脚手架生成的技能：{'、'.join(skipped)}")
        if shared:
            summary.append(f"已导入 {shared} 个共享资源文件（技能集合根目录和分组目录下的非技能内容）")
        if agents is not None:
            summary.append(f"已导入 {len(agent_files)} 个 agents 文件" if agent_files else "agents/ 中的文件已是最新")
        result.text = "\n".join([*summary, *notes, *([result.text] if result.text else [])])
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
        if module_id == "globalHooks":
            skeleton["hooks"] = []
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


# —— hook list / enable / disable（globalHooks 模块的便捷入口）——

def _global_hooks(tree: Tree, entry: dict) -> list:
    if "globalHooks" not in (entry.get("modules") or {}):
        return []
    data = tree.read_bytes(_module_rel(entry, "globalHooks"))
    try:
        value = fsio.parse_json(data) if data is not None else {}
    except fsio.JsonError:
        return []
    return list(value.get("hooks") or []) if isinstance(value, dict) else []


def hook_list(root: Path) -> CommandResult:
    from scaffold.lib.issues import Report
    from scaffold.modules.global_hooks.catalog import catalog

    tree = Tree(root)
    _, entry = entry_of(tree)
    enabled = _global_hooks(tree, entry)
    hooks, lines = [], []
    for hook_id, spec in catalog().items():
        hooks.append({"id": hook_id, "title": spec.title, "description": spec.description,
                      "enabled": hook_id in enabled})
        lines.append(f"{hook_id:<18} {'已启用' if hook_id in enabled else '未启用':<6} {spec.title}：{spec.description}")
    lines.append("产物检查钩子 artifact_guard 始终启用，不在此列；启用的钩子记在 modules/globalHooks.json")
    return CommandResult(Report(), extra={"hooks": hooks}, text="\n".join(lines))


def hook_toggle(root: Path, hook_ids: list, *, enable: bool) -> CommandResult:
    """在 modules/globalHooks.json 的 hooks 中加入或去掉钩子：模块未启用时先启用，去光了就关闭模块。"""
    from scaffold.lib.issues import Report
    from scaffold.modules.global_hooks.catalog import catalog

    available = catalog()
    unknown = [hook_id for hook_id in hook_ids if hook_id not in available]
    if unknown:
        raise UsageError(f"没有全局钩子 {'、'.join(unknown)}，可用：{'、'.join(available)}")
    tree = Tree(root)
    _, entry = entry_of(tree)
    current = _global_hooks(tree, entry)
    if enable:
        updated = current + [hook_id for hook_id in dict.fromkeys(hook_ids) if hook_id not in current]
    else:
        updated = [hook_id for hook_id in current if hook_id not in hook_ids]
    if updated == current:
        return CommandResult(Report(), text="全局钩子没有变化")
    if not updated:
        return module_disable(root, "globalHooks")
    return module_enable(root, "globalHooks", ["hooks=" + json.dumps(updated)])
