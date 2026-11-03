"""new：以种子或 --answers 为起点生成核心配置，再执行 doctor（interfaces.md §1.4，D56）。

交互式问答在后续版本提供（docs/priorities.md）；现在只支持 --yes，回答取自 --from 的种子和 --answers。
"""

from __future__ import annotations

import re
from pathlib import Path

from scaffold import resources
from scaffold.build.load import MODULE_KEYS
from scaffold.commands import CommandResult
from scaffold.commands.doctor import doctor
from scaffold.commands.edit import import_skill
from scaffold.lib import derive, fsio
from scaffold.lib.issues import UsageError
from scaffold.lib.tree import Tree

TEMPLATES = ("blank", "lite", "fullstack")
SCHEMA_REF = re.compile(r'("\$schema"\s*:\s*")[^"]*(")')
PLUGIN_FIELDS = ("id", "name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def schema_ref(rel: str) -> str:
    if rel == "plugin.scaffold.json":
        return "./.scaffold/plugin-scaffold.schema.json"
    if rel.startswith("modules/"):
        return f"../.scaffold/modules/{Path(rel).name.replace('.json', '.schema.json')}"
    return "./.scaffold/workflow.schema.json"


def rewrite_schema(rel: str, data: bytes) -> bytes:
    text = fsio.decode(data)
    return SCHEMA_REF.sub(lambda match: match.group(1) + schema_ref(rel) + match.group(2), text, count=1).encode("utf-8")


def seed_files(template: str) -> dict:
    """种子：入口文件、workflow.json、入口引用的模块配置，以及清单透传引用的文件（Q12.1）。"""
    if template == "blank":
        return {}
    base = f"examples/{template}"
    entry = fsio.parse_json(resources.read_bytes(f"{base}/plugin.scaffold.json"))
    files = {"plugin.scaffold.json": resources.read_bytes(f"{base}/plugin.scaffold.json")}
    references = [entry.get("workflow", "./workflow.json")] + list((entry.get("modules") or {}).values())
    for ref in references:
        rel = ref[2:] if ref.startswith("./") else ref
        files[rel] = resources.read_bytes(f"{base}/{rel}")
    seeded = {rel: rewrite_schema(rel, data) for rel, data in files.items()}
    for key in ("mcpServers", "hooks"):
        ref = entry.get("plugin", {}).get(key)
        if ref:
            rel = ref[2:] if ref.startswith("./") else ref
            if resources.exists(f"{base}/{rel}"):
                seeded[rel] = resources.read_bytes(f"{base}/{rel}")
    return seeded


def load_answers(source: str | None) -> dict | None:
    if source is None:
        return None
    import sys

    try:
        data = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
        answers = fsio.parse_json(data, source)
    except OSError as error:
        raise UsageError(f"无法读取 --answers {source}: {error}") from None
    except fsio.JsonError as error:
        raise UsageError(f"--answers 不是合法的 JSON：{error.describe()}") from None
    if not isinstance(answers, dict):
        raise UsageError("--answers 必须是 JSON 对象")
    return answers


def workflow_from(nodes: list) -> dict:
    groups = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or node.get("stage") not in derive.GROUPS:
            raise UsageError(f"--answers 的 nodes[{index}] 缺少 stage（biz、dev 或 ops）")
        item = {key: node[key] for key in ("id", "seq", "name", "skill", "outputs", "terminal") if key in node}
        groups.setdefault(node["stage"], []).append(item)
    return {"$schema": "./.scaffold/workflow.schema.json",
            "nodes": {group: groups[group] for group in derive.GROUPS if group in groups}}


def apply_answers(files: dict, answers: dict, template: str) -> tuple:
    """返回 (files, 要导入的技能)；写了的类别整体替换种子中的对应内容（interfaces.md §1.4）。"""
    entry = fsio.parse_json(files["plugin.scaffold.json"]) if "plugin.scaffold.json" in files else {
        "$schema": "./.scaffold/plugin-scaffold.schema.json", "scaffoldVersion": 1, "plugin": {}}
    changed = False
    if isinstance(answers.get("plugin"), dict):
        entry["plugin"] = {**entry.get("plugin", {}), **answers["plugin"]}
        entry["plugin"] = {key: entry["plugin"][key] for key in PLUGIN_FIELDS + ("mcpServers", "hooks")
                           if key in entry["plugin"]}
        changed = True
    if "nodes" in answers:
        if not isinstance(answers["nodes"], list) or not answers["nodes"]:
            raise UsageError("--answers 的 nodes 必须是非空数组")
        workflow_rel = (entry.get("workflow") or "./workflow.json")[2:]
        files[workflow_rel] = fsio.dump_json(workflow_from(answers["nodes"]))
    for key in MODULE_KEYS:
        if key not in answers or answers[key] is None:
            continue
        rel = f"modules/{key}.json"
        files[rel] = fsio.dump_json({"$schema": schema_ref(rel), **answers[key]})
        entry.setdefault("modules", {})[key] = f"./{rel}"
        changed = True
    if changed or "plugin.scaffold.json" not in files:
        files["plugin.scaffold.json"] = fsio.dump_json(entry)
    skills = answers.get("skills") or {}
    if not isinstance(skills, dict):
        raise UsageError("--answers 的 skills 必须是对象：技能名 → 导入目录或 null")
    return files, skills


def new(target: Path, *, template: str = "blank", answers: dict | None = None, yes: bool = False) -> CommandResult:
    if not yes:
        raise UsageError("交互式向导在后续版本提供；现在请加 --yes，并用 --from 或 --answers 给出回答")
    if template not in TEMPLATES:
        raise UsageError(f"--from 只能是 {'、'.join(TEMPLATES)}")
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise UsageError(f"目标目录 {target} 必须不存在或为空")
    files = seed_files(template)
    skills = {}
    if answers is not None:
        files, skills = apply_answers(files, answers, template)
    if template == "blank" and (answers is None or "nodes" not in answers or "plugin" not in answers):
        raise UsageError("--from blank 时 --answers 必须给出 plugin 和 nodes")
    tree = Tree(target, files)
    bound = {node.get("skill") for node in (answers or {}).get("nodes", []) if isinstance(node, dict)}
    issues = []
    for skill, source in skills.items():
        overlay, found, _ = import_skill(tree, skill, Path(source) if source else None, bound=skill in bound)
        if source:
            files.update(overlay)
            tree = Tree(target, files)
        issues += found
    result = doctor(target, overlay=files, extra_issues=issues)
    if not result.report.failed():
        (target / "hooks").mkdir(parents=True, exist_ok=True)
    return result

