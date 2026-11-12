"""读取入口文件及其引用的文件，按 Schema 校验结构（scaffold.md 单元 3，D46）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold.build.versions import entry_outdated
from scaffold.lib import fsio, jsonschema
from scaffold.lib.issues import Issue, UsageError, error, warning
from scaffold.lib.tree import Tree

ENTRY = "plugin.scaffold.json"
PUBLIC_MODULE_KEYS = ("board", "session", "knowledge", "artifactSync")
# 保留旧插件的全局钩子配置，以便继续构建。
MODULE_KEYS = (*PUBLIC_MODULE_KEYS, "globalHooks")
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
    hooks: object = None                         # hooks/hooks.json 现有内容（含开发者条目），没有时为 None

    @property
    def root(self):
        return self.tree.root


def rel_path(ref: str) -> str:
    return ref[2:] if ref.startswith("./") else ref


HOOKS_FILE = "hooks/hooks.json"     # 宿主钩子配置：脚手架维护自己的条目，开发者的条目写在同一个文件（D61）


def hook_events(value) -> tuple | None:
    """钩子配置的 (事件 → 条目列表, 是否包在 "hooks" 键下)；结构不对时返回 None。

    两种写法都接受：DevClaw 插件常用的顶层事件 {"PreToolUse": [...]}，以及 {"hooks": {"PreToolUse": [...]}}。
    """
    if not isinstance(value, dict):
        return None
    wrapped = isinstance(value.get("hooks"), dict)
    events = value["hooks"] if wrapped else value
    if not all(isinstance(items, list) and all(isinstance(item, dict) for item in items) for items in events.values()):
        return None
    return events, wrapped


def _parse(tree: Tree, rel: str, issues: list[Issue]):
    data = tree.read_bytes(rel)
    try:
        return data, fsio.parse_json(data, rel)
    except fsio.JsonError as problem:
        issues.append(error("INPUT_SCHEMA", problem.describe(), file=rel,
                            hint="修正 JSON 语法；Schema 和核心配置都必须是严格 JSON（D43）"))
        return data, None


TODO_MARK = "[TODO"
# 可以带着占位先生成、打包前再填的位置（D56：module enable artifactSync 预填的产物简述）：Schema → 值所在映射的指针前缀
SOFT_TODO = {"modules/artifactSync.schema.json": ("/artifacts/", "/extraPaths/")}


def todo_fields(value, pointer: str = ""):
    """核心配置中还没填写的 [TODO: …] 占位：(JSON Pointer, 占位文字, 是否是对象的键)。"""
    if isinstance(value, str):
        if TODO_MARK in value:
            yield pointer, value, False
    elif isinstance(value, dict):
        for key, item in value.items():
            child = f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}"
            if TODO_MARK in str(key):
                yield child, str(key), True
            yield from todo_fields(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from todo_fields(item, f"{pointer}/{index}")


def _check(value, schema_name: str, rel: str, issues: list[Issue]) -> bool:
    """Schema 校验，并逐项报出没填的 [TODO: …] 占位（TODO_FIELD，D63；new --skeleton 写出的骨架靠它提示）。

    占位报 error，doctor 不生成；只有 SOFT_TODO 中的简述报 warning，可以先生成，package 时由 TODO_PLACEHOLDER 拦下。
    占位所在位置的 Schema 问题由 TODO_FIELD 代替，不再另报 INPUT_SCHEMA。
    """
    schema = jsonschema.load_schema(schema_name)
    problems = jsonschema.validate(value, schema)
    todos = list(todo_fields(value))
    soft_prefixes = SOFT_TODO.get(schema_name, ())
    for todo, text, is_key in todos:
        soft = not is_key and todo.startswith(soft_prefixes) if soft_prefixes else False
        make = warning if soft else error
        issues.append(make("TODO_FIELD", f"还没填写：{text}", file=rel, pointer=todo,
                           hint="按占位中的说明填好" + ("；打包前必须填完" if soft else "，填完才能生成插件")))
    remaining = [(pointer, reason) for pointer, reason in problems
                 if not any(pointer == todo or pointer.startswith(todo + "/") for todo, _, _ in todos)]
    for pointer, reason in remaining:
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
    hooks = None
    hooks_ref = (entry.get("plugin") or {}).get("hooks")
    if hooks_ref is not None and rel_path(hooks_ref) != HOOKS_FILE:
        issues.append(error("PLUGIN_HOOKS_PATH", f"plugin.hooks 只能是 ./{HOOKS_FILE}", file=ENTRY, pointer="/plugin/hooks",
                            hint="钩子配置固定在 hooks/hooks.json：脚手架维护自己的条目，你的条目写在同一个文件里；"
                                 "也可以去掉这个字段"))
    if tree.is_file(HOOKS_FILE):
        _, hooks = _parse(tree, HOOKS_FILE, issues)
        if hooks is not None and hook_events(hooks) is None:
            issues.append(error("PLUGIN_HOOKS_INVALID", f"{HOOKS_FILE} 的结构不对：要求事件名 → 条目数组，条目是对象",
                                file=HOOKS_FILE, hint='写成 {"PreToolUse": [{"matcher": …, "hooks": […]}]}，'
                                                      '或包在 {"hooks": {…}} 下'))
    if any(issue.level == "error" for issue in issues):
        return None, issues
    return Inputs(tree, entry, workflow, modules, files, digests, hooks), issues
