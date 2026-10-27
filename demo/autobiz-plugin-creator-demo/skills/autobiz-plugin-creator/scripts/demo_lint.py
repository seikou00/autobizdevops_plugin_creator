#!/usr/bin/env python3
"""演示版配置检查：JSON Schema 结构检查、部分 lint 语义规则和 build 预览。

只读核心配置，不写任何文件；生成插件用 demo_build.py，模拟宿主调用用 demo_simulate.py。
Issue 的 code 和格式与正式版一致（references/input-config.md §7.2，interfaces.md §1.3）。
依赖构建记录的规则（PLUGIN_ID_CHANGED、LAYOUT_CHANGED、BUILD_STALE）和 check 级规则不检查。

用法：python3 demo_lint.py <插件目录> [--preview] [--json] [--strict]
退出码：0 没有 error；1 有 error（--strict 时 warning 也算）；2 用法错误。
"""

import argparse
import copy
import functools
import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

SCHEMA_FILES = {
    "entry": "plugin-scaffold.schema.json",
    "workflow": "workflow.schema.json",
    "board": "modules/board.schema.json",
    "session": "modules/session.schema.json",
    "knowledge": "modules/knowledge.schema.json",
    "artifactSync": "modules/artifactSync.schema.json",
}
MODULE_KEYS = ("board", "session", "knowledge", "artifactSync")
RESERVED_PATHS = {"state.json", "hooks.ndjson", "sync-status.json", "ARTIFACT_CATALOG.json"}
COMMAND_PLACEHOLDERS = {"python", "pluginPath", "skillPath", "projectPath", "featureDir", "feature", "nodeId",
                        "repos", "gitRanges"}
TEXT_PLACEHOLDERS = {
    "dialogTips": {"pluginWorkspace", "projectDir", "projectCode"},
    "systemPromptInject": {"pluginPath", "pluginWorkspace", "projectDir", "feature"},
}
PLACEHOLDER = re.compile(r"\$\{([^}]*)\}")
TYPE_NAMES = {"object": "对象", "array": "数组", "string": "字符串", "boolean": "布尔值",
              "integer": "整数", "number": "数字", "null": "null"}
PATTERN_HINTS = {
    "^[a-z0-9]+(-[a-z0-9]+)*$": "只能用小写字母和数字，单词之间用 - 连接",
    "^[a-z][a-z0-9_]*$": "以小写字母开头，只能含小写字母、数字和下划线",
    "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$": "以小写字母开头，只能含小写字母、数字和下划线，可以用 . 分段",
    "^\\d+\\.\\d+\\.\\d+(-[0-9A-Za-z.-]+)?$": "应为 semver，例如 0.1.0",
    "^(?!~)(?!.*\\\\)(?!.*:)(?!(.*/)?\\.{1,2}(/|$))(?!\\.git(/|$))[^/]+(/[^/]+)*$":
        "应为相对项目目录的路径：不能以 / 或 ~ 开头，不能含 \\、:、. 或 .. 段，不能是 .git 或在 .git 下",
}
TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


class UsageError(Exception):
    pass


class Report:
    def __init__(self):
        self.issues = []
        self.notes = []

    def add(self, level, code, file, pointer, message, hint=""):
        self.issues.append({"level": level, "code": code, "file": file, "pointer": pointer,
                            "message": message, "hint": hint})

    def count(self, level):
        return sum(issue["level"] == level for issue in self.issues)


# —— JSON Schema：只实现本仓库 Schema 用到的 draft-07 关键字 ——

def escape(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def schema_errors(value, schema, root, pointer=""):
    """返回 [(JSON Pointer, 说明)]。$ref 只支持本文件内的 #/definitions/<name>。"""
    if "$ref" in schema:
        return schema_errors(value, root["definitions"][schema["$ref"].rsplit("/", 1)[-1]], root, pointer)
    expected = schema.get("type")
    if expected is not None:
        names = expected if isinstance(expected, list) else [expected]
        if not any(TYPES[name](value) for name in names):
            return [(pointer, "应为" + "或".join(TYPE_NAMES[name] for name in names))]
    errors = []
    if "const" in schema and not same(value, schema["const"]):
        errors.append((pointer, f"只能是 {json.dumps(schema['const'], ensure_ascii=False)}"))
    if "enum" in schema and not any(same(value, item) for item in schema["enum"]):
        errors.append((pointer, "只能取 " + "、".join(json.dumps(item, ensure_ascii=False) for item in schema["enum"])))
    if "not" in schema and not schema_errors(value, schema["not"], root, pointer):
        reserved = schema["not"].get("enum")
        errors.append((pointer, f"{value} 是保留名，不能使用" if reserved else "不符合互斥约束"))
    for option in schema.get("allOf", []):
        errors.extend(schema_errors(value, option, root, pointer))
    if "oneOf" in schema:
        matched = sum(not schema_errors(value, option, root, pointer) for option in schema["oneOf"])
        if matched != 1:
            choices = [option["required"][0] for option in schema["oneOf"] if option.get("required")]
            if len(choices) == len(schema["oneOf"]):
                errors.append((pointer, "必须且只能提供 " + "、".join(choices) + " 中的一个"))
            else:
                errors.append((pointer, "不符合任何一种允许的写法" if matched == 0 else "同时符合多种写法"))
    if "if" in schema:
        branch = "then" if not schema_errors(value, schema["if"], root, pointer) else "else"
        if branch in schema:
            errors.extend(schema_errors(value, schema[branch], root, pointer))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append((pointer, "不能为空" if schema["minLength"] == 1 else f"至少 {schema['minLength']} 个字符"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append((pointer, f"不能超过 {schema['maxLength']} 个字符"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            hint = PATTERN_HINTS.get(schema["pattern"], f"应匹配 {schema['pattern']}")
            errors.append((pointer, f"{json.dumps(value, ensure_ascii=False)} 格式不对：{hint}"))
    if TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((pointer, f"不能小于 {schema['minimum']}"))
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append((pointer, f"必须大于 {schema['exclusiveMinimum']}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append((pointer, f"至少需要 {schema['minItems']} 项"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append((pointer, f"最多 {schema['maxItems']} 项"))
        if schema.get("uniqueItems"):
            keys = [json.dumps(item, sort_keys=True) for item in value]
            if len(keys) != len(set(keys)):
                errors.append((pointer, "不能有重复项"))
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], root, f"{pointer}/{index}"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append((pointer, f"缺少必填字段 {key}"))
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            child = f"{pointer}/{escape(key)}"
            if "propertyNames" in schema:
                errors.extend((child, f"键名 {message}") for _, message in
                              schema_errors(key, schema["propertyNames"], root, child))
            if key in properties:
                errors.extend(schema_errors(item, properties[key], root, child))
            elif extra is False:
                allowed = "、".join(name for name in properties if name != "$schema")
                errors.append((child, f"不支持字段 {key}" + (f"，可用字段：{allowed}" if allowed else "")))
            elif isinstance(extra, dict):
                errors.extend(schema_errors(item, extra, root, child))
    return errors


# —— 读取 ——

def schema_dir():
    """优先用技能自带的 schemas/，在脚手架仓库中运行时退回仓库根目录的 schemas/。"""
    for base in Path(__file__).resolve().parents:
        if (base / "schemas" / SCHEMA_FILES["workflow"]).is_file():
            return base / "schemas"
    raise UsageError("找不到 schemas/ 目录")


@functools.lru_cache(maxsize=None)
def load_schemas():
    directory = schema_dir()
    return {kind: json.loads((directory / name).read_text(encoding="utf-8")) for kind, name in SCHEMA_FILES.items()}


MISSING = object()


def resolve(schema, root):
    while "$ref" in schema:
        schema = root["definitions"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def fill_defaults(value, schema, root):
    """按 Schema 的 default 就地补全缺省字段，返回 value。默认值只写在 Schema 中，lint 和 build 都经由这里取。

    只往已有的对象里补字段；缺省的对象只有 Schema 给了 default（例如 {}）才会创建，所以 knowledgeSedimentation、
    source 这类按需开启的块不会被凭空补出来。oneOf 只进入匹配的那一种写法。推导出来的默认值（例如 workflowLabel
    取 plugin.name）不在 Schema 中，由 build 计算。
    """
    schema = resolve(schema, root)
    for option in schema.get("allOf", []):
        fill_defaults(value, option, root)
    for option in schema.get("oneOf", []):
        if not schema_errors(value, option, root):
            fill_defaults(value, option, root)
            break
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key, item in properties.items():
            if key not in value:
                default = item.get("default", resolve(item, root).get("default", MISSING))
                if default is MISSING:
                    continue
                value[key] = copy.deepcopy(default)
            fill_defaults(value[key], item, root)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for key, item in value.items():
                if key not in properties:
                    fill_defaults(item, extra, root)
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for item in value:
            fill_defaults(item, schema["items"], root)
    return value


def with_defaults(data, kind):
    """返回补全了默认值的副本；看板、会话模块没有引用时传 {}，得到全部默认值。"""
    schema = load_schemas()[kind]
    return fill_defaults(copy.deepcopy(data), schema, schema)


def load_json(path, label, report):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report.add("error", "INPUT_SCHEMA", label, "",
                   f"不是合法的 JSON：第 {error.lineno} 行第 {error.colno} 列，{error.msg}")
    except (OSError, UnicodeDecodeError) as error:
        report.add("error", "INPUT_SCHEMA", label, "", f"无法读取：{error}")
    return None


def check_schema(data, kind, label, schemas, report):
    errors = schema_errors(data, schemas[kind], schemas[kind])
    for pointer, message in errors:
        report.add("error", "INPUT_SCHEMA", label, pointer, message, "按 Schema 修改字段名、类型或取值")
    return not errors


def load(root, report):
    """返回 {kind: 数据}，只包含通过 Schema 的文件；另返回各文件的相对路径。"""
    entry_path = root / "plugin.scaffold.json"
    if not entry_path.is_file():
        raise UsageError(f"找不到入口文件 plugin.scaffold.json：{root}")
    schemas = load_schemas()
    configs, labels = {}, {"entry": "plugin.scaffold.json"}
    entry = load_json(entry_path, labels["entry"], report)
    if entry is None:
        return configs, labels
    if check_schema(entry, "entry", labels["entry"], schemas, report):
        configs["entry"] = with_defaults(entry, "entry")
    refs = with_defaults(entry, "entry") if isinstance(entry, dict) else {}
    workflow_ref = refs.get("workflow")
    labels["workflow"] = workflow_ref[2:] if isinstance(workflow_ref, str) and workflow_ref.startswith("./") \
        else "workflow.json"
    workflow_path = root / labels["workflow"]
    if not workflow_path.is_file():
        raise UsageError(f"找不到核心流程文件 {labels['workflow']}")
    workflow = load_json(workflow_path, labels["workflow"], report)
    if workflow is not None and check_schema(workflow, "workflow", labels["workflow"], schemas, report):
        configs["workflow"] = with_defaults(workflow, "workflow")
    modules = refs.get("modules") if isinstance(refs.get("modules"), dict) else {}
    for key in MODULE_KEYS:
        ref = modules.get(key)
        if not isinstance(ref, str) or not ref.startswith("./"):
            continue
        labels[key] = ref[2:]
        path = root / labels[key]
        if not path.is_file():
            report.add("error", "MODULE_FILE_MISSING", labels["entry"], f"/modules/{key}",
                       f"modules.{key} 引用的 {ref} 不存在", f"创建 {ref}，或去掉 modules.{key} 引用")
            continue
        data = load_json(path, labels[key], report)
        if data is not None and check_schema(data, key, labels[key], schemas, report):
            configs[key] = with_defaults(data, key)
    return configs, labels


# —— 语义规则（lint 子集）——

def as_list(paths):
    return [paths] if isinstance(paths, str) else list(paths)


def path_problem(value):
    if value.startswith("/") or "\\" in value or ":" in value:
        return "不能是绝对路径，也不能含 \\ 或 :"
    if ".." in PurePosixPath(value).parts:
        return "不能含 .. 段"
    if value in RESERVED_PATHS:
        return f"{value} 是保留文件名"
    return ""


def prefix(node_id):
    return node_id.rsplit(".", 1)[-1]


def is_git(spec):
    return isinstance(spec, dict) and "git" in spec


def git_settings(spec):
    return spec["git"]


def output_paths(spec):
    """输出写成路径、路径数组或 {path, optional}，统一返回路径列表；git 产物没有路径。"""
    if is_git(spec):
        return []
    return as_list(spec["path"] if isinstance(spec, dict) else spec)


def check_git_output(git, labels, label, pointer, report):
    if git["repos"] == "deployUnits" and "knowledge" not in labels:
        report.add("error", "GIT_OUTPUT_INVALID", label, f"{pointer}/git/repos",
                   "repos 为 deployUnits，但没有启用知识模块，看板上没有发布单元可选",
                   "启用知识模块，或把 repos 写成 \"project\" 或相对项目目录的路径数组")
    if isinstance(git["repos"], list):
        for index, path in enumerate(git["repos"]):
            if path_problem(path):
                report.add("error", "PATH_UNSAFE", label, f"{pointer}/git/repos/{index}",
                           f"仓库路径 {path} {path_problem(path)}", "写相对项目目录的路径")
    unknown = sorted({name for name in PLACEHOLDER.findall(git["branch"]) if name != "feature"})
    if unknown:
        report.add("error", "GIT_OUTPUT_INVALID", label, f"{pointer}/git/branch",
                   "branch 使用了不支持的占位符：" + "、".join(unknown), "只能用 ${feature}")


def input_id(item):
    return item["id"] if isinstance(item, dict) else item


def find_skill_dirs(root, skill):
    """按 skills/<skill>/、skills/*/<skill>/ 查找含 SKILL.md 的技能目录，返回全部匹配（相对插件根目录）。"""
    skills = root / "skills"
    matches = [Path("skills", skill)] if (skills / skill / "SKILL.md").is_file() else []
    if skills.is_dir():
        matches += sorted(Path("skills", group.name, skill) for group in skills.iterdir()
                          if group.is_dir() and group.name != skill and (group / skill / "SKILL.md").is_file())
    return matches


def skill_dir(root, skill):
    matches = find_skill_dirs(root, skill)
    return matches[0] if matches else Path("skills", skill)


def rules(workflow):
    return workflow.get("rules", {})


def flow_nodes(workflow):
    """按流程顺序返回 [(节点, JSON Pointer, 位置)]。动态阶段的节点排在 insertAfter 节点之后；
    位置是 (主干序号, 插入序号)，主干节点的插入序号为 0；insertAfter 无效的阶段排在最后。"""
    nodes = workflow["nodes"]
    index_of = {node["id"]: index for index, node in enumerate(nodes)}
    inserted = {}
    for stage_index, stage in enumerate(rules(workflow).get("dynamicStages", [])):
        inserted.setdefault(index_of.get(stage["insertAfter"], len(nodes)), []).append((stage_index, stage))
    result = []
    for index in range(len(nodes) + 1):
        if index < len(nodes):
            result.append((nodes[index], f"/nodes/{index}", (index, 0)))
        offset = 1
        for stage_index, stage in inserted.get(index, []):
            for node_index, node in enumerate(stage["nodes"]):
                result.append((node, f"/rules/dynamicStages/{stage_index}/nodes/{node_index}", (index, offset)))
                offset += 1
    return result


def node_checkpoints(node):
    if node.get("terminal"):
        return ["archived"]
    return [f"{prefix(node['id'])}_in_progress", f"{prefix(node['id'])}_done"]


def main_checkpoints(workflow):
    """主干 checkpoint 链，产物同步的 allowedFrom 沿它推导。"""
    return [checkpoint for node in workflow["nodes"] for checkpoint in node_checkpoints(node)]


def all_checkpoints(workflow):
    return [checkpoint for node, _, _ in flow_nodes(workflow) for checkpoint in node_checkpoints(node)]


def check_command(root, command, label, pointer, report, skill_path=None):
    if "\n" in command or "\r" in command:
        report.add("error", "COMMAND_INVALID", label, pointer, "命令不能换行", "写成一行；需要多个步骤时放进一个脚本")
        return
    try:
        args = shlex.split(command)
    except ValueError as error:
        report.add("error", "COMMAND_INVALID", label, pointer, f"无法按 POSIX 规则拆分参数：{error}", "检查引号是否成对")
        return
    unknown = sorted({name for name in PLACEHOLDER.findall(command) if name not in COMMAND_PLACEHOLDERS})
    if unknown:
        report.add("error", "COMMAND_INVALID", label, pointer, "使用了不支持的占位符：" + "、".join(unknown),
                   "可用占位符：" + "、".join("${" + name + "}" for name in sorted(COMMAND_PLACEHOLDERS)))
    bases = {"${pluginPath}/": root}
    if skill_path:
        bases["${skillPath}/"] = root / skill_path
    for arg in args:
        for marker, base in bases.items():
            if arg.startswith(marker) and not (base / arg[len(marker):]).is_file():
                report.add("warning", "COMMAND_SCRIPT_MISSING", label, pointer,
                           f"命令引用的 {arg} 不存在", "校验器由开发者编写；demo_build.py --validator-stubs 可以先生成骨架")


def check_workflow(root, configs, labels, report):
    label, workflow = labels["workflow"], configs["workflow"]
    flow = flow_nodes(workflow)
    ids, prefixes, producers, closed, current = {}, {}, {}, set(), None
    for node, pointer, position in flow:
        node_id = node["id"]
        if node_id in ids:
            report.add("error", "NODE_DUP", label, f"{pointer}/id", f"节点 id {node_id} 与 {ids[node_id]} 处的节点重复")
        else:
            ids[node_id] = pointer
            other = node_id if node.get("terminal") else prefixes.setdefault(prefix(node_id), node_id)
            if other != node_id:
                report.add("error", "CHECKPOINT_DUP", label, f"{pointer}/id",
                           f"{node_id} 与 {other} 的最后一段都是 {prefix(node_id)}，推导出的 checkpoint 重复",
                           "修改其中一个节点 id 的最后一段")
        stage = node.get("stage")
        if stage != current:
            if current is not None:
                closed.add(current)
            if stage in closed:
                report.add("error", "STAGE_ORDER", label, f"{pointer}/stage",
                           f"阶段 {stage} 的节点没有连续排列：{node_id} 与前面同阶段的节点之间隔着其他阶段",
                           "调整节点顺序，让同一阶段的节点排在一起")
            current = stage
        for artifact, spec in node.get("outputs", {}).items():
            if is_git(spec):
                items = git_settings(spec)
                check_git_output(items, labels, label, f"{pointer}/outputs/{escape(artifact)}", report)
                if artifact not in producers:
                    producers[artifact] = (position, node_id, items)
                elif producers[artifact][2] != items:
                    report.add("error", "GIT_OUTPUT_INVALID" if isinstance(producers[artifact][2], dict) else "OUTPUT_PATH_CONFLICT",
                               label, f"{pointer}/outputs/{escape(artifact)}",
                               f"产物 {artifact} 在 {producers[artifact][1]} 中的写法与这里不一致", "同一产物再次输出时写法必须一致")
                continue
            items, paths = output_paths(spec), spec["path"] if isinstance(spec, dict) else spec
            for item_index, item in enumerate(items):
                problem = path_problem(item)
                if problem:
                    suffix = ("/path" if isinstance(spec, dict) else "") + (f"/{item_index}" if isinstance(paths, list) else "")
                    report.add("error", "PATH_UNSAFE", label, f"{pointer}/outputs/{escape(artifact)}{suffix}",
                               f"产物 {artifact} 的路径 {item} {problem}", "改成相对 FEATURE_DIR 的 POSIX 路径")
            if artifact not in producers:
                producers[artifact] = (position, node_id, items)
            elif isinstance(producers[artifact][2], dict):
                report.add("error", "OUTPUT_PATH_CONFLICT", label, f"{pointer}/outputs/{escape(artifact)}",
                           f"产物 {artifact} 在 {producers[artifact][1]} 中是 git 产物，这里是文件", "同一产物再次输出时写法必须一致")
            elif producers[artifact][2] != items:
                report.add("error", "OUTPUT_PATH_CONFLICT", label, f"{pointer}/outputs/{escape(artifact)}",
                           f"产物 {artifact} 在 {producers[artifact][1]} 中的路径是 {'、'.join(producers[artifact][2])}，这里是 {'、'.join(items)}",
                           "同一产物再次输出时路径必须与第一次一致")
            else:
                report.add("warning", "OUTPUT_REDECLARED", label, f"{pointer}/outputs/{escape(artifact)}",
                           f"产物 {artifact} 已由 {producers[artifact][1]} 输出，这里再次输出（以第一个节点为生产者）")
        skill, matches = node["skill"], find_skill_dirs(root, node["skill"])
        if not matches:
            report.add("warning", "SKILL_MISSING", label, f"{pointer}/skill",
                       f"skills/{skill}/SKILL.md 和 skills/*/{skill}/SKILL.md 都不存在", f"build 会在 skills/{skill}/ 生成技能桩文件")
        elif len(matches) > 1:
            report.add("error", "SKILL_AMBIGUOUS", label, f"{pointer}/skill",
                       f"技能 {skill} 出现在多处：" + "、".join(path.as_posix() for path in matches), "只保留一处技能目录")
        directory = matches[0] if matches else Path("skills", skill)
        if "validate" in node:
            check_command(root, node["validate"], label, f"{pointer}/validate", report, directory)
    for node, pointer, position in flow:
        for input_index, item in enumerate(node.get("inputs", [])):
            artifact, input_pointer = input_id(item), f"{pointer}/inputs/{input_index}"
            if artifact not in producers:
                report.add("error", "INPUT_UNKNOWN", label, input_pointer, f"{node['id']} 的输入 {artifact} 没有任何节点输出",
                           f"在前面的节点 outputs 中定义 {artifact}，或检查拼写")
            elif producers[artifact][0] >= position:
                producer = producers[artifact][1]
                where = "本节点" if producer == node["id"] else f"后续节点 {producer} "
                report.add("error", "INPUT_FORWARD", label, input_pointer, f"{node['id']} 的输入 {artifact} 由{where}产出",
                           f"调整节点顺序，让 {producer} 排在 {node['id']} 之前，或从 {node['id']} 的 inputs 中去掉 {artifact}")
    check_flow_rules(workflow, label, report)
    return producers


def check_flow_rules(workflow, label, report):
    nodes = workflow["nodes"]
    main_ids = [node["id"] for node in nodes]
    for index, node in enumerate(nodes):
        if not node.get("terminal"):
            continue
        if index != len(nodes) - 1:
            report.add("error", "TERMINAL_INVALID", label, f"/nodes/{index}/terminal",
                       f"终态节点 {node['id']} 不是最后一个主干节点", "把它移到最后，或去掉 terminal")
        for field in ("outputs", "validate"):
            if field in node:
                report.add("error", "TERMINAL_INVALID", label, f"/nodes/{index}/{field}",
                           f"终态节点 {node['id']} 不能写 {field}", "终态节点只有 archived 一个 checkpoint，进入时只检查输入")
    stage_ids, anchors = set(), {}
    for stage_index, stage in enumerate(rules(workflow).get("dynamicStages", [])):
        pointer, anchor = f"/rules/dynamicStages/{stage_index}", stage["insertAfter"]
        if stage["id"] in stage_ids:
            report.add("error", "DYNAMIC_STAGE_INVALID", label, f"{pointer}/id", f"动态阶段 id {stage['id']} 重复")
        stage_ids.add(stage["id"])
        following = main_ids.index(anchor) + 1 if anchor in main_ids else None
        if following is None:
            report.add("error", "DYNAMIC_STAGE_INVALID", label, f"{pointer}/insertAfter",
                       f"insertAfter 指向的 {anchor} 不是主干节点")
        elif following == len(nodes) or nodes[following - 1].get("terminal") or nodes[following].get("terminal"):
            report.add("error", "DYNAMIC_STAGE_INVALID", label, f"{pointer}/insertAfter",
                       f"{anchor} 后面没有非终态的主干节点，动态阶段无处衔接", "insertAfter 改为更靠前的节点")
        elif anchor in anchors:
            report.add("error", "DYNAMIC_STAGE_INVALID", label, f"{pointer}/insertAfter",
                       f"{anchor} 后面已经插入了动态阶段 {anchors[anchor]}", "合并成一个动态阶段")
        anchors.setdefault(anchor, stage["id"])
        for node_index, node in enumerate(stage["nodes"]):
            if node.get("terminal"):
                report.add("error", "TERMINAL_INVALID", label, f"{pointer}/nodes/{node_index}/terminal",
                           f"动态阶段中的节点 {node['id']} 不能是终态节点")
    all_ids = {node["id"] for node, _, _ in flow_nodes(workflow)}
    skip = rules(workflow).get("skip")
    for index, node_id in enumerate(skip.get("locked", []) if isinstance(skip, dict) else []):
        if node_id not in all_ids:
            report.add("error", "FLOW_NODE_UNKNOWN", label, f"/rules/skip/locked/{index}",
                       f"rules.skip.locked 中的 {node_id} 不是 workflow 中的节点")


def check_board(configs, labels, producers, report):
    label, board, workflow = labels["board"], configs["board"], configs["workflow"]
    nodes = [node for node, _, _ in flow_nodes(workflow)]
    node_ids = {node["id"] for node in nodes}
    display = board.get("display", {})
    for key in display.get("nodes", {}):
        if key not in node_ids:
            report.add("error", "BOARD_NODE_UNKNOWN", label, f"/display/nodes/{escape(key)}",
                       f"display.nodes 中的 {key} 不是 workflow 中的节点（含动态阶段节点）")
    stage_ids = {stage["id"] for stage in rules(workflow).get("dynamicStages", [])}
    for key in display.get("dynamicStages", {}):
        if key not in stage_ids:
            report.add("error", "BOARD_NODE_UNKNOWN", label, f"/display/dynamicStages/{escape(key)}",
                       f"display.dynamicStages 中的 {key} 不是 rules.dynamicStages 中的动态阶段")
    known = all_checkpoints(workflow)
    for key in display.get("checkpointLabels", {}):
        if key not in known:
            report.add("error", "CHECKPOINT_LABEL_UNKNOWN", label, f"/display/checkpointLabels/{escape(key)}",
                       f"checkpoint {key} 不存在", "可用的 checkpoint：" + "、".join(known))
    for key in display.get("artifacts", {}):
        if key not in producers:
            report.add("error", "ARTIFACT_REF_UNKNOWN", label, f"/display/artifacts/{escape(key)}",
                       f"产物 {key} 没有任何节点输出")
    for field, allowed in TEXT_PLACEHOLDERS.items():
        text = display.get(field)
        if text is None:
            continue
        unknown = sorted({name for name in PLACEHOLDER.findall(text) if name not in allowed})
        if unknown:
            report.add("error", "PLACEHOLDER_UNKNOWN", label, f"/display/{field}",
                       f"{field} 使用了不允许的占位符：" + "、".join(unknown),
                       "可用占位符：" + "、".join("${" + name + "}" for name in sorted(allowed)))
    if "systemPromptInject" in display and "FEATURE_DIR" not in display["systemPromptInject"]:
        report.add("warning", "FEATURE_DIR_MISSING", label, "/display/systemPromptInject",
                   "覆写后的 systemPromptInject 不含 FEATURE_DIR", "技能依赖 FEATURE_DIR 定位产物目录，建议保留")
    capabilities = board.get("capabilities", {})
    module_skills = set()
    if capabilities.get("knowledgeSedimentation", {}).get("enabled"):
        module_skills.add(capabilities["knowledgeSedimentation"]["slashSkill"])
    if "artifactSync" in configs:
        module_skills.add(configs["artifactSync"]["skillName"])
    skills = {node["skill"] for node in nodes} | module_skills | {""}
    for key, override in display.get("nodes", {}).items():
        for state, action in override.get("nextAction", {}).items():
            if "slashSkill" in action and action["slashSkill"] not in skills:
                report.add("warning", "SLASH_SKILL_UNKNOWN", label,
                           f"/display/nodes/{escape(key)}/nextAction/{state}/slashSkill",
                           f"slashSkill {action['slashSkill']} 既不是节点技能也不是模块技能",
                           "如果是 DevClaw 提供的技能，可以忽略这条警告")


def check_artifact_sync(configs, labels, producers, report):
    """产物同步模块（modules/artifactSync.json，引用即启用）。"""
    label, sync, workflow = labels["artifactSync"], configs["artifactSync"], configs["workflow"]
    nodes = [node for node, _, _ in flow_nodes(workflow)]
    if sync["skillName"] in {node["skill"] for node in nodes}:
        report.add("error", "MODULE_SKILL_CONFLICT", label, "/skillName", f"产物同步技能名 {sync['skillName']} 与节点技能重名")
    names, chain = set(all_checkpoints(workflow)), main_checkpoints(workflow)
    allowed_from = sync.get("allowedFrom")
    if allowed_from:
        target = allowed_from.split(":", 1)[0] if ":" in allowed_from else None
        main_ids = {node["id"] for node in workflow["nodes"]}
        if (target and target not in main_ids) or (not target and allowed_from not in chain):
            report.add("error", "MODULE_OPTION", label, "/allowedFrom",
                       f"allowedFrom 指向的 {allowed_from} 不存在或不在主干上",
                       "allowedFrom 只沿主干推导；动态阶段节点的 checkpoint 写进 allowedCheckpoints")
    for field in ("allowedCheckpoints", "excludeCheckpoints"):
        for index, name in enumerate(sync.get(field, [])):
            if name not in names:
                report.add("error", "MODULE_OPTION", label, f"/{field}/{index}", f"checkpoint {name} 不存在")
    for artifact in sync["artifacts"]:
        if artifact not in producers:
            report.add("error", "ARTIFACT_REF_UNKNOWN", label, f"/artifacts/{escape(artifact)}", f"产物 {artifact} 没有任何节点输出")
        elif isinstance(producers[artifact][2], dict):
            report.add("error", "ARTIFACT_REF_UNKNOWN", label, f"/artifacts/{escape(artifact)}", f"产物 {artifact} 是 git 产物，不能同步")


def check_session(root, configs, labels, report):
    label, session = labels["session"], configs["session"]
    workflow = configs.get("workflow")
    node_ids = {node["id"] for node, _, _ in flow_nodes(workflow)} if workflow else None
    policies = session.get("policies", {})
    targets = [("/policies/default", policies["default"])] if "default" in policies else []
    for key, policy in policies.get("nodes", {}).items():
        pointer = f"/policies/nodes/{escape(key)}"
        if node_ids is not None and key not in node_ids:
            report.add("error", "POLICY_NODE_UNKNOWN", label, pointer, f"policies.nodes 中的 {key} 不是 workflow 中的节点")
        targets.append((pointer, policy))
    for pointer, policy in targets:
        for index, path in enumerate(policy.get("subagentConfig", {}).get("customSubagentFiles", [])):
            if not (root / path).is_file():
                report.add("warning", "SUBAGENT_FILE_MISSING", label,
                           f"{pointer}/subagentConfig/customSubagentFiles/{index}", f"外挂资源 {path} 不存在",
                           "会话入口会跳过该文件；需要时在插件根目录下创建它，或从列表中去掉")


def check_entry(configs, labels, report):
    plugin = configs["entry"]["plugin"]
    if "interface" in plugin and not plugin["codexManifest"]:
        report.add("warning", "INTERFACE_UNUSED", labels["entry"], "/plugin/interface",
                   "声明了 plugin.interface，但 codexManifest 为 false，不会生成 Codex 清单")
    if configs["entry"]["runtime"]["layout"] == "legacy":
        report.add("warning", "LAYOUT_LEGACY", labels["entry"], "/runtime/layout",
                   "legacy 布局只用于迁移已有插件：不能与另一个 legacy 插件装在同一个项目中")


def lint(root):
    report = Report()
    configs, labels = load(root, report)
    producers = None
    if "entry" in configs:
        check_entry(configs, labels, report)
    if "workflow" in configs:
        producers = check_workflow(root, configs, labels, report)
    else:
        report.notes.append(f"{labels.get('workflow', 'workflow.json')} 结构有误，依赖它的语义规则这次没有检查")
    if "board" in configs and producers is not None:
        check_board(configs, labels, producers, report)
    if "artifactSync" in configs and producers is not None:
        check_artifact_sync(configs, labels, producers, report)
    if "session" in configs:
        check_session(root, configs, labels, report)
    knowledge_root = configs.get("knowledge", {}).get("root")
    if knowledge_root and path_problem(knowledge_root):
        report.add("error", "PATH_UNSAFE", labels["knowledge"], "/root",
                   f"知识目录 {knowledge_root} {path_problem(knowledge_root)}")
    return report, configs, labels


# —— build 预览：只说明会生成什么 ——

def preview(root, configs, labels):
    entry, workflow = configs["entry"], configs["workflow"]
    nodes, flow = workflow["nodes"], [node for node, _, _ in flow_nodes(workflow)]
    plugin = entry["plugin"]
    board = configs.get("board") or with_defaults({}, "board")
    session = configs.get("session") or with_defaults({}, "session")
    knowledge = configs.get("knowledge")
    display, capabilities = board["display"], board.get("capabilities", {})
    layout, meta_root = entry["runtime"]["layout"], entry["runtime"]["metaRoot"]
    meta_dir = meta_root if layout == "legacy" else f"{meta_root}/{plugin['id']}"
    group_default = display.get("workflowLabel", plugin["name"])
    artifact_labels, groups, node_rows, actions = {}, [], [], []
    for node in flow:
        for artifact, spec in node.get("outputs", {}).items():
            artifact_labels.setdefault(artifact, display.get("artifacts", {}).get(artifact, (output_paths(spec) or [artifact])[0]))

    def optional(item):
        return "（可选）" if isinstance(item, dict) and item.get("optional") else ""

    def output_text(artifact, spec):
        if is_git(spec):
            repos = git_settings(spec)["repos"]
            return f"{artifact_labels[artifact]}（git：{repos if isinstance(repos, str) else '、'.join(repos)}）"
        paths = output_paths(spec)
        text = "、".join(paths) if artifact_labels[artifact] in paths else f"{artifact_labels[artifact]}（{'、'.join(paths)}）"
        return text + optional(spec)

    for index, node in enumerate(nodes):
        group = node.get("stage", group_default)
        if not groups or groups[-1]["group"] != group:
            groups.append({"group": group, "nodes": []})
        groups[-1]["nodes"].append(node["id"])
        override = display.get("nodes", {}).get(node["id"], {}).get("nextAction", {})
        following = nodes[index + 1] if index + 1 < len(nodes) else None
        node_rows.append({
            "id": node["id"], "label": node["name"], "group": group, "skill": node["skill"],
            "checkpoints": node_checkpoints(node),
            "inputs": [artifact_labels.get(input_id(item), input_id(item)) + optional(item) for item in node.get("inputs", [])],
            "outputs": [output_text(artifact, spec) for artifact, spec in node.get("outputs", {}).items()],
            "validate": node.get("validate", ""),
            "policy": session.get("policies", {}).get("nodes", {}).get(node["id"]),
        })
        actions.append({"node": node["id"],
                        "active": override.get("active", {}).get("slashSkill", node["skill"]),
                        "done": override.get("done", {}).get("slashSkill", following["skill"] if following else "")})
    flow_rules = []
    for stage in rules(workflow).get("dynamicStages", []):
        flow_rules.append(f"动态阶段「{stage['name']}」：插在 {stage['insertAfter']} 之后，节点 "
                          + "、".join(node["id"] for node in stage["nodes"])
                          + f"，默认 {stage.get('defaultDecision', 'pending')}")
    skip = rules(workflow).get("skip")
    if skip:
        locked = skip["locked"] if isinstance(skip, dict) else []
        flow_rules.append("跳过节点：" + ("锁定 " + "、".join(locked) if locked else "除终态节点外都可跳过"))
    flow_rules += [f"终态节点 {node['id']}：只有 archived" for node in nodes if node.get("terminal")]
    commands = ["project_status", "feature_status", "create_project", "create_feature", "dynamic_workflow",
                "session_context_inject", "plugin_dir_hook", "dialog_tips", "system_prompt_inject"]
    if skip:
        commands.append("skip_node")
    board_keys = ["apiVersion", "inspectCommands", "workflow", "checkpointSuffixState"]
    runtime_config = ["runtime.json", "flow.json", "session.json"]
    module_files = []
    if knowledge is not None:
        commands += ["knowledge_path", "deploy_units"] + (["pull_knowledge"] if "source" in knowledge else [])
        board_keys += ["supported_deploy_units"] + (["agentsRepo"] if "source" in knowledge else [])
        runtime_config.append("knowledge.json")
        module_files.append("runtime/knowledge/inspect_deploy_units.py")
        assembly = knowledge["assembly"]
        if assembly["enabled"] and assembly["assembler"] == "plugin":
            module_files += ["runtime/knowledge/render_collected_session_context.py", "runtime/knowledge/collect-knowledge.js"]
        if "source" in knowledge:
            module_files.append("runtime/knowledge/sync_knowledge.py")
    if capabilities.get("knowledgeSedimentation", {}).get("enabled"):
        board_keys.append("knowledge_config")
    sync = configs.get("artifactSync")
    if sync is not None:
        if sync["entry"]["enabled"]:
            board_keys.append("artifact_sync")
        module_files.append(f"skills/{sync['skillName']}/")
    generated = ["plugin.json", "board_core/board_config.json"] + [f"runtime/config/{name}" for name in runtime_config] \
        + ["runtime/build-manifest.json"]
    if plugin.get("codexManifest"):
        generated.insert(1, ".codex-plugin/plugin.json")
    seeded, updated = [], []
    for node in flow:
        directory = skill_dir(root, node["skill"])
        skill_file = f"{directory.as_posix()}/SKILL.md"
        target = seeded if not (root / skill_file).is_file() else updated
        if skill_file not in seeded and skill_file not in updated:
            target.append(skill_file)
    seeded += [".gitignore"]
    return {
        "plugin": {"id": plugin["id"], "name": plugin["name"], "version": plugin["version"], "layout": layout},
        "featureDir": f"<项目目录>/{meta_dir}/features/<feature>/",
        "checkpoints": main_checkpoints(workflow), "flowRules": flow_rules,
        "groups": groups, "nodes": node_rows, "nextActions": actions,
        "platforms": board["target"]["platforms"],
        "inspectCommands": commands, "boardConfigKeys": board_keys,
        "files": {"generated": generated,
                  "managed": ["runtime/workflow/update_state.py", "runtime/adapters/*",
                              "runtime/session/render_session_context.py", "runtime/common/query.py、engine.py",
                              ".scaffold/*.schema.json"],
                  "module": module_files, "seeded": seeded, "stateBlockUpdated": updated},
    }


def print_preview(view):
    plugin = view["plugin"]
    print("\n── build 预览（只说明，不写文件；执行 demo_build.py 才会生成）──")
    print(f"插件：{plugin['id']} · {plugin['name']} {plugin['version']}，{plugin['layout']} 布局")
    print(f"产物目录：{view['featureDir']}")
    print("checkpoint 链（主干）：" + " → ".join(view["checkpoints"]))
    if view["flowRules"]:
        print("流程规则（演示版 build 不支持，build 时会报 DEMO_UNSUPPORTED）：")
        for rule in view["flowRules"]:
            print(f"  {rule}")
    print("看板节点：")
    for group in view["groups"]:
        print(f"  分组「{group['group']}」")
        for row in (row for row in view["nodes"] if row["id"] in group["nodes"]):
            print(f"    {row['id']} {row['label']}：技能 /{row['skill']}")
            print(f"      输入：{'、'.join(row['inputs']) or '—'}；输出：{'、'.join(row['outputs']) or '—'}")
            print(f"      完成时校验：{row['validate'] or '无（只检查产物存在）'}")
            if row["policy"]:
                print(f"      运行策略：{json.dumps(row['policy'], ensure_ascii=False)}")
    print("看板带出的技能：")
    for action in view["nextActions"]:
        done = f"/{action['done']}" if action["done"] else "（流程结束）"
        active = f"/{action['active']}" if action["active"] else "（不带出）"
        print(f"  {action['node']}：未开始、进行中 → {active}；完成后 → {done}")
    print(f"宿主命令（{'、'.join(view['platforms'])} 各一组）：{'、'.join(view['inspectCommands'])}")
    print(f"board_config 顶层键：{'、'.join(view['boardConfigKeys'])}")
    files = view["files"]
    print("build 会生成：")
    for kind in ("generated", "managed", "module", "seeded"):
        if files[kind]:
            print(f"  {kind:<9} {'、'.join(files[kind])}")
    if files["module"]:
        print("  （演示版 build 暂不支持知识模块和产物同步，build 时会报 DEMO_UNSUPPORTED）")
    if files["stateBlockUpdated"]:
        print(f"  已存在的技能只更新状态接入托管片段：{'、'.join(files['stateBlockUpdated'])}")
    print("simulate 会做什么：")
    print("  临时目录中建项目 → create_project → create_feature demo → 每个节点依次："
          "session_context_inject → 推进 _in_progress → 写入桩产物 → 推进 _done（执行校验命令，"
          "可用 --skip-validate 跳过）→ feature_status")


def print_report(root, report, labels):
    print(f"检查 {root}")
    by_file = {}
    for issue in report.issues:
        by_file.setdefault(issue["file"], []).append(issue)
    for file in sorted(by_file, key=lambda name: list(labels.values()).index(name) if name in labels.values() else 99):
        print(f"  {file}")
        for issue in by_file[file]:
            print(f"    {issue['level']} {issue['code']} {issue['pointer'] or '（文件）'}")
            print(f"      {issue['message']}")
            if issue["hint"]:
                print(f"      建议：{issue['hint']}")
    print(f"结果：{report.count('error')} 个 error，{report.count('warning')} 个 warning")
    for note in report.notes:
        print(f"注意：{note}；修正后请重新检查")


def main(argv=None):
    parser = argparse.ArgumentParser(description="演示版配置检查（Schema + 部分 lint 规则 + build 预览）")
    parser.add_argument("plugin_dir", nargs="?", default=".", help="插件根目录，含 plugin.scaffold.json")
    parser.add_argument("--preview", action="store_true", help="没有 error 时输出 build 预览")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--strict", action="store_true", help="warning 也视为 error")
    args = parser.parse_args(argv)
    root = Path(args.plugin_dir).expanduser().resolve()
    try:
        report, configs, labels = lint(root)
    except UsageError as error:
        if args.json:
            print(json.dumps({"ok": False, "usageError": str(error), "issues": [], "written": []}, ensure_ascii=False))
        else:
            print(f"用法错误：{error}", file=sys.stderr)
        return 2
    failed = report.count("error") > 0 or (args.strict and report.count("warning") > 0)
    view = preview(root, configs, labels) if args.preview and not failed else None
    if args.json:
        result = {"ok": not failed, "issues": report.issues, "notes": report.notes, "written": []}
        if view is not None:
            result["preview"] = view
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(root, report, labels)
        if view is not None:
            print_preview(view)
        elif args.preview:
            print("\n有 error，先修正再看 build 预览。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
