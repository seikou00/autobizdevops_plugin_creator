#!/usr/bin/env python3
"""演示版 build：把核心配置编译成可以装进 DevClaw 的插件。

先执行 demo_lint 的全部检查，有 error 时不写任何文件。生成内容按归属处理（docs/README.md §4）：
- generated：plugin.json、board_core/board_config.json、runtime/config/*、runtime/build-manifest.json，每次重写；
- managed：runtime/ 下的框架入口与内部库、.scaffold/ 下的 Schema；被手改过时拒绝覆盖（--force 强制覆盖）；
- seeded：技能桩、模板桩、校验器骨架（--validator-stubs）、.gitignore，只在缺失时创建；
  已有的 SKILL.md 只更新 state、artifacts 两个托管片段。

演示版不支持知识模块和产物同步；不生成 boardEvents（DevClaw 尚未支持看板事件推送）。

用法：python3 demo_build.py <插件目录> [--validator-stubs] [--force] [--dry-run] [--json]
退出码：0 成功；1 有 error，没有写入任何文件；2 用法错误。
"""

import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_lint  # noqa: E402
from demo_lint import Report, UsageError, as_list, prefix  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_TEMPLATE = SKILL_DIR / "assets" / "runtime"
SCAFFOLD_VERSION = "0.1.0-demo"
CORE_VERSION = "0.1.0-demo"
BUILTIN_POLICY = {"agentMode": "solo", "toolCustomConfig": {"task": {"enabled": True}}}
STATE_LABELS = {"not_started": "未开始", "in_progress": "进行中", "done": "已完成"}
FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}
LEGACY_REFS = re.compile(r"hooks/update_state\.py|hooks/update_checkpoint\.py|hooks/init_workspace\.py"
                         r"|\$\{pluginPath\}/inspect_state\.py")
COMMANDS = {
    "project_status": '{py} "${pluginPath}/runtime/adapters/inspect_state.py" --mode project '
                      '--workspace "${pluginWorkspace}" --projects ${projectDirs...}',
    "feature_status": '{py} "${pluginPath}/runtime/adapters/inspect_state.py" --mode run '
                      '--workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}"',
    "create_project": '{py} "${pluginPath}/runtime/adapters/init_workspace.py" '
                      '--workspace "${pluginWorkspace}" --project "${projectDir}"',
    "create_feature": '{py} "${pluginPath}/runtime/adapters/init_feature.py" --workspace "${pluginWorkspace}" '
                      '--project "${projectDir}" --feature "${feature}" --selected-deployUnit ${selectedDeployUnits}',
    "dynamic_workflow": '{py} "${pluginPath}/runtime/adapters/inspect_workflow_templates.py"',
}
SESSION_COMMAND = ('{py} "${pluginPath}/runtime/session/render_session_context.py" --platform {platform} '
                   '--plugin-workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" '
                   '--selected-deployUnit ${selectedDeployUnits} --session-workspace-path "${sessionWorkspacePath}"')


def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def deep_merge(base, override):
    merged = json.loads(json.dumps(base))
    for key, value in (override or {}).items():
        merged[key] = deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) \
            else value
    return merged


class Plan:
    """build 的内存结果：先算完全部内容，没有 error 时再统一写盘。"""

    def __init__(self, root, previous):
        self.root, self.previous = root, previous
        self.files, self.ownership, self.regions = {}, {}, {}

    def add(self, path, data, ownership):
        self.files[path] = data
        self.ownership[path] = ownership


# —— 编译：核心配置 → 中间表示 → board_config / flow / session / runtime ——

class Compiled:
    def __init__(self, root, configs, labels):
        entry, self.nodes = configs["entry"], configs["workflow"]["nodes"]
        self.root, self.configs, self.labels, self.plugin = root, configs, labels, entry["plugin"]
        self.board, self.session = configs.get("board", {}), configs.get("session", {})
        self.display, self.target = self.board.get("display", {}), self.board.get("target", {})
        self.layout = entry.get("runtime", {}).get("layout", "isolated")
        self.timeout = entry.get("runtime", {}).get("validateTimeoutSec", 120)
        self.meta = ".autobizdevops" if self.layout == "legacy" else f".autobizdevops/{self.plugin['id']}"
        self.label = self.display.get("workflowLabel", self.plugin["name"])
        self.chain_names = " → ".join(node["name"] for node in self.nodes)
        self.state_labels = {**STATE_LABELS, **self.display.get("stateLabels", {})}
        self.artifacts = {}
        for node in self.nodes:
            for artifact, paths in node.get("outputs", {}).items():
                items = as_list(paths)
                self.artifacts.setdefault(artifact, {
                    "label": self.display.get("artifacts", {}).get(artifact, items[0]),
                    "type": "json" if items[0].endswith(".json") else "file",
                    "paths": items, "producer": node["id"], "array": isinstance(paths, list)})

    def group(self, node):
        return node.get("stage", self.label)

    def checkpoints(self, node):
        return [f"{prefix(node['id'])}_in_progress", f"{prefix(node['id'])}_done"]

    def artifact_def(self, artifact):
        info = self.artifacts[artifact]
        definition = {"id": artifact, "label": info["label"], "artifactType": info["type"],
                      "path": info["paths"][0], "required": True}
        if info["array"]:
            definition["paths"] = info["paths"]
        return definition

    def board_node(self, index, node):
        override = self.display.get("nodes", {}).get(node["id"], {})
        following = self.nodes[index + 1] if index + 1 < len(self.nodes) else None
        active = {"slashSkill": node["skill"], "userMessage": f"请使用 /{node['skill']} 处理当前 Feature，先读取现有状态和产物。",
                  "dialogTips": f"当前阶段：{node['name']}。"}
        active.update(override.get("nextAction", {}).get("active", {}))
        if following:
            done = {"slashSkill": following["skill"],
                    "userMessage": f"请使用 /{following['skill']} 处理当前 Feature，先读取现有状态和产物。",
                    "dialogTips": f"下一阶段：{following['name']}。"}
        else:
            done = {"slashSkill": "", "userMessage": "", "dialogTips": f"{node['name']}已完成。"}
        done.update(override.get("nextAction", {}).get("done", {}))
        output_paths = "、".join(path for item in node.get("outputs", {}) for path in self.artifacts[item]["paths"])
        result = {"id": node["id"], "label": node["name"], "group": self.group(node), "skill": node["skill"],
                  "order": (index + 1) * 10}
        policy = self.session.get("policies", {}).get("nodes", {}).get(node["id"])
        if policy is not None:
            result["runtimePolicy"] = policy
        result.update({
            "description": override.get("description") or (f"{node['name']}；产物：{output_paths}" if output_paths
                                                            else node["name"]),
            "checkpoints": self.checkpoints(node),
            "states": [{"nodeStatus": status, "label": self.state_labels[status], "nextAction": action}
                       for status, action in (("not_started", active), ("in_progress", active), ("done", done))],
            "artifacts": {"inputs": [self.artifact_def(item) for item in node.get("inputs", [])],
                          "outputs": [self.artifact_def(item) for item in node.get("outputs", {})]},
            "validators": []})
        return result

    def inspect_commands(self):
        python = self.target.get("python", {})
        commands = {}
        for platform in self.target.get("platforms", demo_lint.DEFAULT_PLATFORMS):
            py = python.get("win32", "python") if platform == "win32" else python.get("posix", "python3")
            if self.target.get("utf8Mode", True):
                py += " -X utf8"
            group = {key: value.replace("{py}", py) for key, value in COMMANDS.items()}
            group.update({
                "plugin_dir_hook": "${pluginWorkspace}/${projectDir}",
                "dialog_tips": self.display.get("dialogTips", f"当前为{self.label}插件：{self.chain_names}。请描述目标与验收标准。"),
                "system_prompt_inject": self.display.get(
                    "systemPromptInject", f"当前 Feature 为 ${{feature}}。产物目录 FEATURE_DIR=${{pluginWorkspace}}/${{projectDir}}/"
                                          f"{self.meta}/features/${{feature}}。插件根目录 PLUGIN_ROOT=${{pluginPath}}。"),
                "session_context_inject": SESSION_COMMAND.replace("{py}", py).replace("{platform}", platform)})
            commands[platform] = group
        return commands

    def board_config(self):
        chain = [checkpoint for node in self.nodes for checkpoint in self.checkpoints(node)]
        config = {
            "apiVersion": 1,
            "inspectCommands": self.inspect_commands(),
            "workflow": {
                "templates": {"standard": {"kind": "profile", "label": self.label,
                                           "description": self.display.get("workflowDescription", f"{self.chain_names}。")}},
                "checkpoints": {
                    "initial": [chain[0]],
                    "transitions": {checkpoint: chain[index + 1:index + 2] for index, checkpoint in enumerate(chain)},
                    "stageLabels": {checkpoint: f"{node['name']}{'进行中' if checkpoint.endswith('_in_progress') else '完成'}"
                                    for node in self.nodes for checkpoint in self.checkpoints(node)}},
                "nodes": [self.board_node(index, node) for index, node in enumerate(self.nodes)],
                "transitions": [{"id": f"{prefix(node['id'])}-to-{prefix(following['id'])}",
                                 "from": {"nodeId": node["id"], "state": "done"},
                                 "to": {"nodeId": following["id"], "state": "in_progress"}}
                                for node, following in zip(self.nodes, self.nodes[1:])]},
            "checkpointSuffixState": {status: {"nodeStatus": status, "label": self.state_labels[status]}
                                      for status in ("in_progress", "done")},
        }
        sedimentation = self.board.get("capabilities", {}).get("knowledgeSedimentation", {})
        if sedimentation.get("enabled"):
            config["knowledge_config"] = {
                "sync_type": sedimentation.get("syncType", "invoke_session"),
                "nextAction": {"slashSkill": sedimentation.get("slashSkill", "knowledge-sync"),
                               "userMessage": sedimentation.get("userMessage", "请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}"),
                               "dialogTips": sedimentation.get("dialogTips", "发起知识沉淀")}}
        return config

    def flow(self):
        chain = [checkpoint for node in self.nodes for checkpoint in self.checkpoints(node)]
        workflow_file = self.root / self.labels["workflow"]
        return {
            "schema": "autobiz.flow.v1",
            "source": {self.labels["workflow"]: sha256(workflow_file.read_bytes())},
            "stages": list(dict.fromkeys(self.group(node) for node in self.nodes)),
            "artifacts": {artifact: {key: info[key] for key in ("label", "type", "paths", "producer")}
                          for artifact, info in self.artifacts.items()},
            "nodes": [{"id": node["id"], "name": node["name"], "stage": self.group(node), "skill": node["skill"],
                       "order": (index + 1) * 10, "checkpoints": self.checkpoints(node),
                       "inputs": list(node.get("inputs", [])), "outputs": list(node.get("outputs", {})),
                       "templates": [f"skills/{node['skill']}/{template}" for template in node.get("templates", [])],
                       "validate": node.get("validate")} for index, node in enumerate(self.nodes)],
            "checkpoints": {"chain": chain, "initial": chain[0],
                            "labels": {checkpoint: f"{node['name']}{'进行中' if checkpoint.endswith('_in_progress') else '完成'}"
                                       for node in self.nodes for checkpoint in self.checkpoints(node)}},
        }

    def session_config(self):
        policies = self.session.get("policies", {})
        entry = self.session.get("customEntry")
        return {"schema": "autobiz.session.v1",
                "policies": {"default": deep_merge(BUILTIN_POLICY, policies.get("default")),
                             "nodes": policies.get("nodes", {})},
                "parts": [],
                "customEntry": {"command": entry["command"], "timeoutSec": entry.get("timeoutSec", 30)} if entry else None}

    def runtime_config(self):
        return {"schema": "autobiz.runtime.v1", "pluginId": self.plugin["id"], "layout": self.layout,
                "validateTimeoutSec": self.timeout}

    def manifests(self):
        keys = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
        root = {key: self.plugin[key] for key in keys if key in self.plugin}
        root["skills"] = "./skills/"
        for key in ("mcpServers", "hooks"):
            if key in self.plugin:
                root[key] = self.plugin[key]
        result = {"plugin.json": root}
        if self.plugin.get("codexManifest"):
            codex = {"name": self.plugin["id"], "version": self.plugin["version"],
                     "description": self.plugin["description"], "skills": "./skills/"}
            if "mcpServers" in self.plugin:
                codex["mcpServers"] = self.plugin["mcpServers"]
            interface = dict(self.plugin.get("interface", {}))
            interface.setdefault("displayName", self.plugin["name"])
            interface.setdefault("shortDescription", self.plugin["description"])
            codex["interface"] = interface
            result[".codex-plugin/plugin.json"] = codex
        return result


# —— 技能：桩文件与托管片段 ——

def python_command(compiled):
    py = compiled.target.get("python", {}).get("posix", "python3")
    return py + (" -X utf8" if compiled.target.get("utf8Mode", True) else "")


def state_block(compiled, nodes):
    py = python_command(compiled)
    update = f'{py} "${{pluginPath}}/runtime/workflow/update_state.py" --feature "${{feature}}" --checkpoint'
    lines = ["## 技能状态维护", "",
             "> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后重新 build 更新。"
             "Windows 上把 `python3` 换成 `python`。"]
    for node in nodes:
        start, finish = compiled.checkpoints(node)
        if len(nodes) > 1:
            lines += ["", f"### 节点「{node['name']}」（{node['id']}）"]
        lines += ["", "- 技能开始执行：", "  ```", f"  {update} {start}", "  ```",
                  "- 本节点必需产物全部写入 `FEATURE_DIR` 后：", "  ```", f"  {update} {finish}", "  ```"]
        if node.get("validate"):
            lines.append(f"  推进时框架会检查必需产物是否存在，并执行本节点的校验命令 `{node['validate']}`。"
                         "未通过时按返回的错误修正产物后重试，不需要自己调用校验命令。")
        else:
            lines.append("  推进时框架会检查必需产物是否存在。")
        lines.append(f'- 需要修改已完成阶段时：`--checkpoint {start} --reopen --reason "<原因>"`')
    return "\n".join(lines)


def artifacts_block(compiled, nodes):
    lines = ["## 输入、产物与模板", "", "| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |", "|---|---|---|---|"]
    templates = []
    for node in nodes:
        for direction, items in (("输入", node.get("inputs", [])), ("输出", list(node.get("outputs", {})))):
            for item in items:
                info = compiled.artifacts[item]
                lines.append(f"| {direction} | {info['label']} | {'、'.join(f'`{path}`' for path in info['paths'])} | 是 |")
        templates += [f"`${{pluginPath}}/skills/{node['skill']}/{template}`" for template in node.get("templates", [])]
    if len(lines) == 4:
        lines.append("| — | 无 | — | — |")
    if templates:
        lines += ["", "模板：" + "、".join(templates)]
    return "\n".join(lines)


def region(name, content):
    return f"<!-- scaffold:begin {name} -->\n{content}\n<!-- scaffold:end {name} -->"


def region_pattern(name):
    return re.compile(rf"<!-- scaffold:begin {name} -->.*?<!-- scaffold:end {name} -->", re.S)


def frontmatter(text):
    """返回 (frontmatter 结束位置, {顶层键: 值})；没有 frontmatter 时返回 (0, None)。"""
    match = re.match(r"---\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not match:
        return 0, None
    keys = {}
    for line in match.group(1).splitlines():
        found = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if found:
            keys[found.group(1)] = found.group(2).strip().strip("'\"")
    return match.end(), keys


def upsert(text, name, content, after=None):
    block = region(name, content)
    pattern = region_pattern(name)
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    if after and region_pattern(after).search(text):
        position = region_pattern(after).search(text).end()
    else:
        position, _ = frontmatter(text)
        heading = re.compile(r"^# .*$", re.M).search(text, position)
        if heading:
            position = heading.end()
    return text[:position].rstrip("\n") + "\n\n" + block + "\n\n" + text[position:].lstrip("\n")


def stub_skill(compiled, skill, nodes):
    name = nodes[0]["name"]
    return (f"---\nname: {skill}\ndescription: {compiled.plugin['name']} 的「{name}」节点。[TODO: 写明做什么、在什么情况下使用]\n---\n\n"
            f"# {name}\n\n{region('state', state_block(compiled, nodes))}\n\n"
            f"{region('artifacts', artifacts_block(compiled, nodes))}\n\n"
            "（以下为开发者编写的技能正文）\n\n[TODO: 写明本节点的工作步骤、产物要求和完成标准]\n")


VALIDATOR_STUB = '''#!/usr/bin/env python3
"""{name}节点的完成校验（脚手架生成的骨架，业务规则由开发者补充）。

退出码 0 表示通过；不通过时把原因打印在输出末尾，框架会把输出末尾返回给模型。
"""

import argparse
import os
import sys
from pathlib import Path

OUTPUTS = {outputs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-dir", default=os.environ.get("FEATURE_DIR", "."))
    args, _ = parser.parse_known_args()
    directory = Path(args.feature_dir)
    problems = []
    for pattern in OUTPUTS:
        files = [path for path in sorted(directory.glob(pattern)) if path.is_file()]
        if not files:
            problems.append(f"{{pattern}} 不存在")
        problems += [f"{{path.relative_to(directory).as_posix()}} 是空文件" for path in files
                     if not path.read_text(encoding="utf-8", errors="replace").strip()]
    # TODO: 在这里补充业务校验，例如必需的章节、结论字段
    if problems:
        print("校验未通过：" + "；".join(problems))
        return 1
    print("校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def plan_skills(compiled, plan, report, validator_stubs):
    by_skill = {}
    for node in compiled.nodes:
        by_skill.setdefault(node["skill"], []).append(node)
    for skill, nodes in by_skill.items():
        path = f"skills/{skill}/SKILL.md"
        label = path
        if len(nodes) > 1:
            report.add("warning", "SKILL_SHARED", label, "", f"{skill} 被 {len(nodes)} 个节点共用，技能需要自行区分 checkpoint")
        existing = compiled.root / path
        previous = plan.previous.get("files", {}).get(path, {}).get("regions", {})
        if not existing.is_file():
            text = stub_skill(compiled, skill, nodes)
            plan.add(path, text.encode("utf-8"), "seeded")
            for folder in ("templates", "scripts"):
                plan.add(f"skills/{skill}/{folder}/", None, "seeded")
        else:
            text = existing.read_text(encoding="utf-8")
            end, keys = frontmatter(text)
            if keys is None:
                report.add("error", "SKILL_FRONTMATTER", label, "", "SKILL.md 缺少 frontmatter（name、description）",
                           "在文件开头加上 ---、name、description、--- 四行")
                continue
            if keys.get("name") != skill:
                report.add("error", "SKILL_NAME_MISMATCH", label, "",
                           f"frontmatter 中的 name 是 {keys.get('name')!r}，节点绑定的技能是 {skill}",
                           "把 name 改成目录名，或修改 workflow.json 中的 skill")
            if not keys.get("description"):
                report.add("error", "SKILL_FRONTMATTER", label, "", "frontmatter 缺少 description", "写明做什么、什么时候使用")
            extra = sorted(set(keys) - FRONTMATTER_KEYS)
            if extra:
                report.add("warning", "SKILL_FRONTMATTER", label, "", f"frontmatter 有多余的键：{'、'.join(extra)}",
                           "DevClaw 不依赖这些键；正式版 import 会把 version、author 迁到 metadata")
            outside = region_pattern("artifacts").sub("", region_pattern("state").sub("", text))
            if LEGACY_REFS.search(outside):
                report.add("warning", "LEGACY_ENTRY_REF", label, "",
                           "技能正文仍引用旧入口（hooks/update_state.py 等），会与新的状态接入说明冲突",
                           "删除正文中旧的状态维护段落，以托管片段为准")
            text = upsert(text, "state", state_block(compiled, nodes))
            if previous.get("artifacts") == "optOut" or ("artifacts" in previous and not region_pattern("artifacts").search(text)):
                plan.regions.setdefault(path, {})["artifacts"] = "optOut"
            else:
                text = upsert(text, "artifacts", artifacts_block(compiled, nodes), after="state")
            plan.add(path, text.encode("utf-8"), "seeded")
        for node in nodes:
            for template in node.get("templates", []):
                if not (compiled.root / "skills" / skill / template).is_file():
                    plan.add(f"skills/{skill}/{template}",
                             f"# {Path(template).stem}\n\n[TODO: 模板内容]\n".encode("utf-8"), "seeded")
            if validator_stubs and node.get("validate"):
                for arg in shlex.split(node["validate"]):
                    if arg.startswith("${skillPath}/") and arg.endswith(".py"):
                        relative = f"skills/{skill}/{arg[len('${skillPath}/'):]}"
                        if not (compiled.root / relative).is_file():
                            outputs = [path for item in node.get("outputs", {}) for path in compiled.artifacts[item]["paths"]]
                            plan.add(relative, VALIDATOR_STUB.format(name=node["name"], outputs=json.dumps(
                                outputs, ensure_ascii=False)).encode("utf-8"), "seeded")


# —— 计划与写盘 ——

def plan_build(root, configs, labels, report, validator_stubs):
    previous_path = root / "runtime" / "build-manifest.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}
    compiled = Compiled(root, configs, labels)
    if previous and previous.get("pluginId") != compiled.plugin["id"]:
        report.add("error", "PLUGIN_ID_CHANGED", labels["entry"], "/plugin/id",
                   f"plugin.id 从 {previous.get('pluginId')} 改成了 {compiled.plugin['id']}，已有项目的状态会找不到",
                   "发布前确需修改时，删除 runtime/build-manifest.json 后重新 build")
    if previous and previous.get("layout") != compiled.layout:
        report.add("error", "LAYOUT_CHANGED", labels["entry"], "/runtime/layout",
                   f"runtime.layout 从 {previous.get('layout')} 改成了 {compiled.layout}，已有项目的状态会找不到",
                   "发布前确需修改时，删除 runtime/build-manifest.json 后重新 build")
    if "knowledge" in labels:
        report.add("error", "DEMO_UNSUPPORTED", labels["entry"], "/modules/knowledge", "演示版 build 不支持知识模块",
                   "去掉 modules.knowledge 引用后再 build")
    if compiled.board.get("capabilities", {}).get("artifactSync", {}).get("enabled"):
        report.add("error", "DEMO_UNSUPPORTED", labels.get("board", "modules/board.json"), "/capabilities/artifactSync",
                   "演示版 build 不支持产物同步", "把 artifactSync.enabled 改为 false 后再 build")
    plan = Plan(root, previous)
    for path, manifest in compiled.manifests().items():
        plan.add(path, dump(manifest), "generated")
    plan.add("board_core/board_config.json", dump(compiled.board_config()), "generated")
    plan.add("runtime/config/runtime.json", dump(compiled.runtime_config()), "generated")
    plan.add("runtime/config/flow.json", dump(compiled.flow()), "generated")
    plan.add("runtime/config/session.json", dump(compiled.session_config()), "generated")
    for source in sorted(RUNTIME_TEMPLATE.rglob("*.py")):
        if "__pycache__" not in source.parts:
            plan.add(f"runtime/{source.relative_to(RUNTIME_TEMPLATE).as_posix()}", source.read_bytes(), "managed")
    schemas = demo_lint.schema_dir()
    for source in sorted(schemas.rglob("*.schema.json")):
        plan.add(f".scaffold/{source.relative_to(schemas).as_posix()}", source.read_bytes(), "managed")
    if not (root / ".gitignore").exists():
        plan.add(".gitignore", b"__pycache__/\n*.pyc\n.DS_Store\ndist/\n", "seeded")
    plan_skills(compiled, plan, report, validator_stubs)
    return plan, compiled


def check_drift(plan, report, force):
    recorded = plan.previous.get("files", {})
    for path, ownership in plan.ownership.items():
        target = plan.root / path
        if ownership != "managed" or not target.is_file():
            continue
        current = sha256(target.read_bytes())
        if current != sha256(plan.files[path]) and current != recorded.get(path, {}).get("sha256") and not force:
            report.add("error", "DRIFT_MANAGED", path, "", f"{path} 被手改过，build 不会覆盖它",
                       "撤销手改；确认要覆盖时加 --force")


def manifest(plan, compiled):
    inputs = {label: sha256((plan.root / label).read_bytes()) for label in compiled.labels.values()}
    files = {}
    for path, data in sorted(plan.files.items()):
        if data is None:
            continue
        record = {"ownership": plan.ownership[path], "sha256": sha256(data)}
        if path.startswith("skills/") and path.endswith("/SKILL.md"):
            text = data.decode("utf-8")
            record["regions"] = {name: sha256(match.group(0).encode("utf-8")) if match else "optOut"
                                 for name, match in ((name, region_pattern(name).search(text)) for name in ("state", "artifacts"))}
            record["regions"].update(plan.regions.get(path, {}))
        files[path] = record
    for path, record in plan.previous.get("files", {}).items():
        target = plan.root / path
        if path not in files and path != "runtime/build-manifest.json" and target.is_file():
            files[path] = {**record, "sha256": sha256(target.read_bytes())}  # 之前生成、这次无需改动的骨架文件
    files = dict(sorted(files.items()))
    modules = {"board": CORE_VERSION, "session": CORE_VERSION}
    return {"schema": "autobiz.build-manifest.v1", "scaffoldVersion": SCAFFOLD_VERSION, "coreVersion": CORE_VERSION,
            "pluginId": compiled.plugin["id"], "layout": compiled.layout, "modules": modules,
            "inputs": inputs, "files": files}


def write(plan, compiled):
    written = {}
    plan.add("runtime/build-manifest.json", dump(manifest(plan, compiled)), "generated")
    for path, data in plan.files.items():
        target = plan.root / path
        if data is None:
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                written.setdefault(plan.ownership[path], []).append(path)
            continue
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        written.setdefault(plan.ownership[path], []).append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="演示版 build：核心配置 → 可安装的插件")
    parser.add_argument("plugin_dir", nargs="?", default=".")
    parser.add_argument("--validator-stubs", action="store_true", help="为缺失的校验器脚本生成骨架")
    parser.add_argument("--force", action="store_true", help="覆盖被手改过的托管文件")
    parser.add_argument("--dry-run", action="store_true", help="只检查和列出将要写入的文件")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.plugin_dir).expanduser().resolve()
    try:
        report, configs, labels = demo_lint.lint(root)
    except UsageError as error:
        print(f"用法错误：{error}", file=sys.stderr)
        return 2
    plan = compiled = None
    if not report.count("error"):
        plan, compiled = plan_build(root, configs, labels, report, args.validator_stubs)
        check_drift(plan, report, args.force)
    failed = report.count("error") > 0
    written = {} if failed or args.dry_run else write(plan, compiled)
    if args.json:
        print(json.dumps({"ok": not failed, "issues": report.issues, "notes": report.notes,
                          "written": sorted(path for paths in written.values() for path in paths)},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0
    demo_lint.print_report(root, report, labels)
    if failed:
        print("\nbuild 未执行：没有写入任何文件。")
        return 1
    if args.dry_run:
        print("\n--dry-run：将写入 " + "、".join(sorted(path for path in plan.files)))
        return 0
    print("\nbuild 完成。")
    names = {"generated": "生成", "managed": "托管", "seeded": "骨架/片段"}
    for ownership in ("generated", "managed", "seeded"):
        if written.get(ownership):
            print(f"  {names[ownership]}（{ownership}）：{'、'.join(sorted(written[ownership]))}")
    if not written:
        print("  所有文件已是最新，没有变化。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
