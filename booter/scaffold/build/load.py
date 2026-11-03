"""读取入口文件及其引用的文件，按 Schema 校验结构（scaffold.md 单元 3，D46）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold.build.versions import entry_outdated
from scaffold.lib import fsio, jsonschema
from scaffold.lib.issues import Issue, UsageError, error
from scaffold.lib.tree import Tree

ENTRY = "plugin.scaffold.json"
MODULE_KEYS = ("board", "session", "knowledge", "artifactSync")
SCHEMAS = {"entry": "plugin-scaffold.schema.json", "workflow": "workflow.schema.json",
           **{key: f"modules/{key}.schema.json" for key in MODULE_KEYS}}


@dataclass(frozen=True)
class Inputs:
    tree: Tree
    entry: dict                                  # 入口文件原文
    workflow: dict                               # workflow.json 原文
    modules: dict = field(default_factory=dict)  # 引用了的模块 → 原文
    files: dict = field(default_factory=dict)    # "entry"、"workflow"、模块键 → 相对插件根的路径
    digests: dict = field(default_factory=dict)  # 相对路径 → 摘要

    @property
    def root(self):
        return self.tree.root


def rel_path(ref: str) -> str:
    return ref[2:] if ref.startswith("./") else ref


def _parse(tree: Tree, rel: str, issues: list[Issue]):
    data = tree.read_bytes(rel)
    try:
        return data, fsio.parse_json(data, rel)
    except fsio.JsonError as problem:
        issues.append(error("INPUT_SCHEMA", problem.describe(), file=rel,
                            hint="修正 JSON 语法；Schema 和核心配置都必须是严格 JSON（D43）"))
        return data, None


def _check(value, schema_name: str, rel: str, issues: list[Issue]) -> bool:
    schema = jsonschema.load_schema(schema_name)
    problems = jsonschema.validate(value, schema)
    for pointer, reason in problems:
        issues.append(error("INPUT_SCHEMA", reason, file=rel, pointer=pointer))
    return not problems


def load(tree: Tree) -> tuple[Inputs | None, list[Issue]]:
    issues: list[Issue] = []
    if not tree.is_file(ENTRY):
        raise UsageError(f"找不到入口文件 {ENTRY}：{tree.path(ENTRY)}")
    files = {"entry": ENTRY}
    digests = {}
    raw, entry = _parse(tree, ENTRY, issues)
    digests[ENTRY] = fsio.digest(raw)
    if entry is None:
        return None, issues
    _check(entry, SCHEMAS["entry"], ENTRY, issues)
    outdated = entry_outdated(entry)
    if outdated:
        issues[:] = [issue for issue in issues if issue.pointer != "/scaffoldVersion"] + outdated
        return None, issues
    if not isinstance(entry, dict) or any(issue.pointer.startswith(("/workflow", "/modules")) for issue in issues):
        return None, issues
    workflow_rel = rel_path(entry.get("workflow", "./workflow.json"))
    if not tree.is_file(workflow_rel):
        raise UsageError(f"入口文件引用的 {workflow_rel} 不存在：{tree.path(workflow_rel)}")
    files["workflow"] = workflow_rel
    raw, workflow = _parse(tree, workflow_rel, issues)
    digests[workflow_rel] = fsio.digest(raw)
    if workflow is not None:
        _check(workflow, SCHEMAS["workflow"], workflow_rel, issues)
    modules = {}
    for key in MODULE_KEYS:
        ref = (entry.get("modules") or {}).get(key)
        if ref is None:
            continue
        rel = rel_path(ref)
        files[key] = rel
        if not tree.is_file(rel):
            issues.append(error("MODULE_FILE_MISSING", f"modules.{key} 引用的 {rel} 不存在", file=ENTRY,
                                pointer=f"/modules/{key}", hint=f"创建 {rel}，或去掉这个引用"))
            continue
        raw, value = _parse(tree, rel, issues)
        digests[rel] = fsio.digest(raw)
        if value is not None:
            _check(value, SCHEMAS[key], rel, issues)
            modules[key] = value
    if any(issue.level == "error" for issue in issues):
        return None, issues
    return Inputs(tree, entry, workflow, modules, files, digests), issues
