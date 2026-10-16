#!/usr/bin/env python3
"""演示版配置检查：JSON Schema 结构检查、部分 lint 语义规则和 build 预览。

只读核心配置，不写任何文件；生成插件用 demo_build.py，模拟宿主调用用 demo_simulate.py。
Issue 的 code 和格式与正式版一致（references/input-config.md §7.2，interfaces.md §1.3）。
依赖构建记录的规则（PLUGIN_ID_CHANGED、LAYOUT_CHANGED、BUILD_STALE）和 check 级规则不检查。

用法：python3 demo_lint.py <插件目录> [--preview] [--json] [--strict]
退出码：0 没有 error；1 有 error（--strict 时 warning 也算）；2 用法错误。
"""

import argparse
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
}
MODULE_KEYS = ("board", "session", "knowledge")
RESERVED_PATHS = {"state.json", "hooks.ndjson", "sync-status.json", "ARTIFACT_CATALOG.json"}
COMMAND_PLACEHOLDERS = {"python", "pluginPath", "skillPath", "projectPath", "featureDir", "feature", "nodeId"}
TEXT_PLACEHOLDERS = {
    "dialogTips": {"pluginWorkspace", "projectDir", "projectCode"},
    "systemPromptInject": {"pluginPath", "pluginWorkspace", "projectDir", "feature"},
}
PLACEHOLDER = re.compile(r"\$\{([^}]*)\}")
DEFAULT_PLATFORMS = ["darwin", "linux", "win32"]
DEFAULT_SYNC_SKILL = "autobizdevops-artifact-sync"
TYPE_NAMES = {"object": "对象", "array": "数组", "string": "字符串", "boolean": "布尔值",
              "integer": "整数", "number": "数字", "null": "null"}
PATTERN_HINTS = {
    "^[a-z0-9]+(-[a-z0-9]+)*$": "只能用小写字母和数字，单词之间用 - 连接",
    "^[a-z][a-z0-9_]*$": "以小写字母开头，只能含小写字母、数字和下划线",
    "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$": "以小写字母开头，只能含小写字母、数字和下划线，可以用 . 分段",
    "^\\d+\\.\\d+\\.\\d+(-[0-9A-Za-z.-]+)?$": "应为 semver，例如 0.1.0",
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
    root_schemas = schema_dir()
    schemas = {kind: json.loads((root_schemas / name).read_text(encoding="utf-8"))
               for kind, name in SCHEMA_FILES.items()}
    configs, labels = {}, {"entry": "plugin.scaffold.json"}
    entry = load_json(entry_path, labels["entry"], report)
    if entry is None:
        return configs, labels
    if check_schema(entry, "entry", labels["entry"], schemas, report):
        configs["entry"] = entry
    refs = entry if isinstance(entry, dict) else {}
    workflow_ref = refs.get("workflow", "./workflow.json")
    labels["workflow"] = workflow_ref[2:] if isinstance(workflow_ref, str) and workflow_ref.startswith("./") \
        else "workflow.json"
    workflow_path = root / labels["workflow"]
    if not workflow_path.is_file():
        raise UsageError(f"找不到核心流程文件 {labels['workflow']}")
    workflow = load_json(workflow_path, labels["workflow"], report)
    if workflow is not None and check_schema(workflow, "workflow", labels["workflow"], schemas, report):
        configs["workflow"] = workflow
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
            configs[key] = data
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


def check_command(root, command, label, pointer, report, skill=None):
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
    if skill:
        bases["${skillPath}/"] = root / "skills" / skill
    for arg in args:
        for marker, base in bases.items():
            if arg.startswith(marker) and not (base / arg[len(marker):]).is_file():
                report.add("warning", "COMMAND_SCRIPT_MISSING", label, pointer,
                           f"命令引用的 {arg} 不存在", "校验器由开发者编写；demo_build.py --validator-stubs 可以先生成骨架")


def check_workflow(root, configs, labels, report):
    label, nodes = labels["workflow"], configs["workflow"]["nodes"]
    ids, prefixes, producers, closed, current = {}, {}, {}, set(), None
    for index, node in enumerate(nodes):
        pointer, node_id = f"/nodes/{index}", node["id"]
        if node_id in ids:
            report.add("error", "NODE_DUP", label, f"{pointer}/id", f"节点 id {node_id} 与第 {ids[node_id] + 1} 个节点重复")
        else:
            ids[node_id] = index
            other = prefixes.setdefault(prefix(node_id), node_id)
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
        for artifact, paths in node.get("outputs", {}).items():
            items = as_list(paths)
            for item_index, item in enumerate(items):
                problem = path_problem(item)
                if problem:
                    suffix = f"/{item_index}" if isinstance(paths, list) else ""
                    report.add("error", "PATH_UNSAFE", label, f"{pointer}/outputs/{escape(artifact)}{suffix}",
                               f"产物 {artifact} 的路径 {item} {problem}", "改成相对 FEATURE_DIR 的 POSIX 路径")
            if artifact not in producers:
                producers[artifact] = (index, node_id, items)
            elif producers[artifact][2] != items:
                report.add("error", "OUTPUT_PATH_CONFLICT", label, f"{pointer}/outputs/{escape(artifact)}",
                           f"产物 {artifact} 在 {producers[artifact][1]} 中的路径是 {'、'.join(producers[artifact][2])}，这里是 {'、'.join(items)}",
                           "同一产物再次输出时路径必须与第一次一致")
            else:
                report.add("warning", "OUTPUT_REDECLARED", label, f"{pointer}/outputs/{escape(artifact)}",
                           f"产物 {artifact} 已由 {producers[artifact][1]} 输出，这里再次输出（以第一个节点为生产者）")
        skill_dir = root / "skills" / node["skill"]
        if not (skill_dir / "SKILL.md").is_file():
            report.add("warning", "SKILL_MISSING", label, f"{pointer}/skill",
                       f"skills/{node['skill']}/SKILL.md 不存在", "build 会生成技能桩文件")
        for template_index, template in enumerate(node.get("templates", [])):
            problem = path_problem(template)
            if problem:
                report.add("error", "PATH_UNSAFE", label, f"{pointer}/templates/{template_index}",
                           f"模板路径 {template} {problem}", "改成相对技能目录的 POSIX 路径")
            elif not (skill_dir / template).is_file():
                report.add("warning", "TEMPLATE_MISSING", label, f"{pointer}/templates/{template_index}",
                           f"skills/{node['skill']}/{template} 不存在", "build 会生成模板桩文件")
        if "validate" in node:
            check_command(root, node["validate"], label, f"{pointer}/validate", report, node["skill"])
    for index, node in enumerate(nodes):
        for input_index, artifact in enumerate(node.get("inputs", [])):
            pointer = f"/nodes/{index}/inputs/{input_index}"
            if artifact not in producers:
                report.add("error", "INPUT_UNKNOWN", label, pointer, f"{node['id']} 的输入 {artifact} 没有任何节点输出",
                           f"在前面的节点 outputs 中定义 {artifact}，或检查拼写")
            elif producers[artifact][0] >= index:
                producer = producers[artifact][1]
                where = "本节点" if producer == node["id"] else f"后续节点 {producer} "
                report.add("error", "INPUT_FORWARD", label, pointer, f"{node['id']} 的输入 {artifact} 由{where}产出",
                           f"调整节点顺序，让 {producer} 排在 {node['id']} 之前，或从 {node['id']} 的 inputs 中去掉 {artifact}")
    return producers


def checkpoints(nodes):
    return [f"{prefix(node['id'])}_{state}" for node in nodes for state in ("in_progress", "done")]


def check_board(configs, labels, producers, report):
    label, board, nodes = labels["board"], configs["board"], configs["workflow"]["nodes"]
    node_ids = {node["id"] for node in nodes}
    display = board.get("display", {})
    for key in display.get("nodes", {}):
        if key not in node_ids:
            report.add("error", "BOARD_NODE_UNKNOWN", label, f"/display/nodes/{escape(key)}",
                       f"display.nodes 中的 {key} 不是 workflow 中的节点")
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
    sync = capabilities.get("artifactSync", {})
    module_skills = set()
    if capabilities.get("knowledgeSedimentation", {}).get("enabled"):
        module_skills.add(capabilities["knowledgeSedimentation"].get("slashSkill", "knowledge-sync"))
    if sync.get("enabled"):
        sync_skill = sync.get("skillName", DEFAULT_SYNC_SKILL)
        module_skills.add(sync_skill)
        if sync_skill in {node["skill"] for node in nodes}:
            report.add("error", "MODULE_SKILL_CONFLICT", label, "/capabilities/artifactSync/skillName",
                       f"产物同步技能名 {sync_skill} 与节点技能重名")
        names = set(checkpoints(nodes))
        allowed_from = sync.get("allowedFrom")
        if allowed_from:
            target = allowed_from.split(":", 1)[0] if ":" in allowed_from else None
            if (target and target not in node_ids) or (not target and allowed_from not in names):
                report.add("error", "MODULE_OPTION", label, "/capabilities/artifactSync/allowedFrom",
                           f"allowedFrom 指向的 {allowed_from} 不存在")
        for field in ("allowedCheckpoints", "excludeCheckpoints"):
            for index, name in enumerate(sync.get(field, [])):
                if name not in names:
                    report.add("error", "MODULE_OPTION", label, f"/capabilities/artifactSync/{field}/{index}",
                               f"checkpoint {name} 不存在")
        node = sync.get("apiDetail", {}).get("node")
        if node and node not in node_ids:
            report.add("error", "MODULE_OPTION", label, "/capabilities/artifactSync/apiDetail/node",
                       f"apiDetail.node 指向的节点 {node} 不存在")
        for index, artifact in enumerate(sync.get("exclude", [])):
            if artifact not in producers:
                report.add("error", "ARTIFACT_REF_UNKNOWN", label, f"/capabilities/artifactSync/exclude/{index}",
                           f"产物 {artifact} 没有任何节点输出")
        for artifact in sync.get("descriptions", {}):
            if artifact not in producers:
                report.add("error", "ARTIFACT_REF_UNKNOWN", label,
                           f"/capabilities/artifactSync/descriptions/{escape(artifact)}", f"产物 {artifact} 没有任何节点输出")
    skills = {node["skill"] for node in nodes} | module_skills | {""}
    for key, override in display.get("nodes", {}).items():
        for state, action in override.get("nextAction", {}).items():
            if "slashSkill" in action and action["slashSkill"] not in skills:
                report.add("warning", "SLASH_SKILL_UNKNOWN", label,
                           f"/display/nodes/{escape(key)}/nextAction/{state}/slashSkill",
                           f"slashSkill {action['slashSkill']} 既不是节点技能也不是模块技能",
                           "如果是 DevClaw 提供的技能，可以忽略这条警告")


def check_session(root, configs, labels, report):
    label, session = labels["session"], configs["session"]
    workflow = configs.get("workflow")
    node_ids = {node["id"] for node in workflow["nodes"]} if workflow else None
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
                report.add("error", "SUBAGENT_FILE_MISSING", label,
                           f"{pointer}/subagentConfig/customSubagentFiles/{index}", f"外挂资源 {path} 不存在",
                           "在插件根目录下创建该文件，或从列表中去掉")
    if "customEntry" in session:
        check_command(root, session["customEntry"]["command"], label, "/customEntry/command", report)


def check_entry(configs, labels, report):
    plugin = configs["entry"]["plugin"]
    if "interface" in plugin and not plugin.get("codexManifest", False):
        report.add("warning", "INTERFACE_UNUSED", labels["entry"], "/plugin/interface",
                   "声明了 plugin.interface，但 codexManifest 为 false，不会生成 Codex 清单")
    if configs["entry"].get("runtime", {}).get("layout") == "legacy":
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
    if "session" in configs:
        check_session(root, configs, labels, report)
    knowledge_root = configs.get("knowledge", {}).get("root")
    if knowledge_root and path_problem(knowledge_root):
        report.add("error", "PATH_UNSAFE", labels["knowledge"], "/root",
                   f"知识目录 {knowledge_root} {path_problem(knowledge_root)}")
    return report, configs, labels


# —— build 预览：只说明会生成什么 ——

def preview(root, configs, labels):
    entry, nodes = configs["entry"], configs["workflow"]["nodes"]
    plugin = entry["plugin"]
    board, session = configs.get("board", {}), configs.get("session", {})
    knowledge = configs.get("knowledge")
    display, capabilities = board.get("display", {}), board.get("capabilities", {})
    layout = entry.get("runtime", {}).get("layout", "isolated")
    meta_dir = ".autobizdevops" if layout == "legacy" else f".autobizdevops/{plugin['id']}"
    group_default = display.get("workflowLabel", plugin["name"])
    artifact_labels, groups, node_rows, actions = {}, [], [], []
    for node in nodes:
        for artifact, paths in node.get("outputs", {}).items():
            artifact_labels.setdefault(artifact, display.get("artifacts", {}).get(artifact, as_list(paths)[0]))
    for index, node in enumerate(nodes):
        group = node.get("stage", group_default)
        if not groups or groups[-1]["group"] != group:
            groups.append({"group": group, "nodes": []})
        groups[-1]["nodes"].append(node["id"])
        override = display.get("nodes", {}).get(node["id"], {}).get("nextAction", {})
        following = nodes[index + 1] if index + 1 < len(nodes) else None
        node_rows.append({
            "id": node["id"], "label": node["name"], "group": group, "skill": node["skill"],
            "checkpoints": [f"{prefix(node['id'])}_in_progress", f"{prefix(node['id'])}_done"],
            "inputs": [artifact_labels.get(item, item) for item in node.get("inputs", [])],
            "outputs": [f"{artifact_labels[item]}（{'、'.join(as_list(paths))}）" if artifact_labels[item] not in as_list(paths)
                        else "、".join(as_list(paths)) for item, paths in node.get("outputs", {}).items()],
            "validate": node.get("validate", ""),
            "policy": session.get("policies", {}).get("nodes", {}).get(node["id"]),
        })
        actions.append({"node": node["id"],
                        "active": override.get("active", {}).get("slashSkill", node["skill"]),
                        "done": override.get("done", {}).get("slashSkill", following["skill"] if following else "")})
    commands = ["project_status", "feature_status", "create_project", "create_feature", "dynamic_workflow",
                "session_context_inject", "plugin_dir_hook", "dialog_tips", "system_prompt_inject"]
    board_keys = ["apiVersion", "inspectCommands", "workflow", "checkpointSuffixState"]
    runtime_config = ["runtime.json", "flow.json", "session.json"]
    module_files = []
    if knowledge is not None:
        commands += ["knowledge_path", "deploy_units"] + (["pull_knowledge"] if "source" in knowledge else [])
        board_keys += ["supported_deploy_units"] + (["agentsRepo"] if "source" in knowledge else [])
        runtime_config.append("knowledge.json")
        module_files.append("runtime/knowledge/inspect_deploy_units.py")
        assembly = knowledge.get("assembly", {})
        if assembly.get("enabled", True) and assembly.get("assembler", "plugin") == "plugin":
            module_files.append("runtime/knowledge/assembler.py")
        if "source" in knowledge:
            module_files.append("runtime/knowledge/sync_knowledge.py")
    if capabilities.get("knowledgeSedimentation", {}).get("enabled"):
        board_keys.append("knowledge_config")
    sync = capabilities.get("artifactSync", {})
    if sync.get("enabled"):
        if sync.get("entry", {}).get("enabled", True):
            board_keys.append("artifact_sync")
        module_files.append(f"skills/{sync.get('skillName', DEFAULT_SYNC_SKILL)}/")
    generated = ["plugin.json", "board_core/board_config.json"] + [f"runtime/config/{name}" for name in runtime_config] \
        + ["runtime/build-manifest.json"]
    if plugin.get("codexManifest"):
        generated.insert(1, ".codex-plugin/plugin.json")
    seeded, updated = [], []
    for node in nodes:
        skill_file = f"skills/{node['skill']}/SKILL.md"
        target = seeded if not (root / skill_file).is_file() else updated
        if skill_file not in seeded and skill_file not in updated:
            target.append(skill_file)
        for template in node.get("templates", []):
            if not (root / "skills" / node["skill"] / template).is_file():
                seeded.append(f"skills/{node['skill']}/{template}")
    seeded += [".gitignore"]
    return {
        "plugin": {"id": plugin["id"], "name": plugin["name"], "version": plugin["version"], "layout": layout},
        "featureDir": f"<项目目录>/{meta_dir}/features/<feature>/",
        "checkpoints": checkpoints(nodes),
        "groups": groups, "nodes": node_rows, "nextActions": actions,
        "platforms": board.get("target", {}).get("platforms", DEFAULT_PLATFORMS),
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
    print("checkpoint 链：" + " → ".join(view["checkpoints"]))
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
