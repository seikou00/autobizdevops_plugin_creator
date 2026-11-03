"""看板模块（core）：宿主命令、看板文案 board.json、知识沉淀入口（input-config.md §4.1、§6）。"""

from __future__ import annotations

import re

from scaffold.build.contribute import CommandSpec, Contribution, FileSpec
from scaffold.lib import derive
from scaffold.lib.issues import error, warning
from scaffold.modules import Module

FILE = "modules/board.json"
PLACEHOLDER = re.compile(r"\$\{([^}]*)\}")
ALLOWED = {
    "dialogTips": ("pluginWorkspace", "projectDir", "projectCode"),
    "systemPromptInject": ("pluginPath", "pluginWorkspace", "projectDir", "feature"),
}
ADAPTERS = ("init_workspace.py", "init_feature.py", "inspect_state.py", "inspect_workflow_templates.py")
KNOWLEDGE_CONFIG = {
    "sync_type": "invoke_session",
    "nextAction": {"slashSkill": "knowledge-sync", "userMessage": "请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}",
                   "dialogTips": "发起知识沉淀"},
}
STATE_ORDER = ("not_started", "in_progress", "done", "archived")


def display_texts(ir, display: dict) -> dict:
    chain = " → ".join(node.name for node in ir.nodes)
    label = display.get("workflowLabel") or ir.plugin["name"]
    meta_root = ir.runtime["metaRoot"]
    return {
        "workflowLabel": label,
        "workflowDescription": display.get("workflowDescription") or f"{chain}。",
        "dialogTips": display.get("dialogTips") or f"当前为{label}插件：{chain}。请描述目标与验收标准。",
        "systemPromptInject": display.get("systemPromptInject") or (
            f"当前 Feature 为 ${{feature}}。产物目录 FEATURE_DIR=${{pluginWorkspace}}/${{projectDir}}/{meta_root}/features/"
            f"${{feature}}。插件根目录 PLUGIN_ROOT=${{pluginPath}}。"),
    }


def _action(skill: str, message: str, tips: str) -> dict:
    return {"slashSkill": skill, "userMessage": message, "dialogTips": tips}


def _use(skill: str) -> str:
    return f"请使用 /{skill} 处理当前 Feature，先读取现有状态和产物。"


def next_actions(ir, node) -> dict:
    current = _action(node.skill, _use(node.skill), f"当前阶段：{node.name}。")
    if node.terminal:
        return {"not_started": current,
                "archived": _action(node.skill, f"请使用 /{node.skill} 查看当前 Feature 的归档状态。",
                                    f"{node.name}已完成。")}
    following = ir.next_node(node.id)
    if following is None:
        done = _action("", "", f"{node.name}已完成。")
    else:
        done = _action(following.skill, _use(following.skill), f"下一阶段：{following.name}。")
    return {"not_started": current, "in_progress": dict(current), "done": done}


def board_config(ir, options: dict) -> dict:
    display = options.get("display", {})
    texts = display_texts(ir, display)
    labels = display.get("stateLabels", {})
    has_terminal = any(node.terminal for node in ir.nodes)
    state_labels = {key: labels[key] for key in STATE_ORDER if key in labels and (key != "archived" or has_terminal)}
    nodes = {}
    for node in ir.nodes:
        nodes.setdefault(node.group, []).append({"id": node.id, "description": node.description,
                                                 "nextAction": next_actions(ir, node)})
    return {
        "schema": "autobiz.board.v1",
        "template": {"id": "standard", "label": texts["workflowLabel"], "description": texts["workflowDescription"]},
        "stateLabels": state_labels,
        "nodes": {group: nodes[group] for group in derive.GROUPS if group in nodes},
        "dynamicStages": {},
    }


class BoardModule(Module):
    def validate(self, ir, options, ctx):
        issues = []
        display = options.get("display", {})
        for key, allowed in ALLOWED.items():
            text = display.get(key)
            if text is None:
                continue
            for name in PLACEHOLDER.findall(text):
                if name not in allowed:
                    issues.append(error("PLACEHOLDER_UNKNOWN", f"display.{key} 中的 ${{{name}}} 不是这个文案允许的占位符",
                                        file=FILE, pointer=f"/display/{key}",
                                        hint="可用：" + "、".join(f"${{{item}}}" for item in allowed)
                                             + "（interfaces.md §3.2）"))
        prompt = display.get("systemPromptInject")
        if prompt is not None and "FEATURE_DIR" not in prompt:
            issues.append(warning("FEATURE_DIR_MISSING", "覆写后的 systemPromptInject 不含 FEATURE_DIR，技能依赖它定位产物目录",
                                  file=FILE, pointer="/display/systemPromptInject"))
        return issues

    def contribute(self, ir, options, ctx):
        texts = display_texts(ir, options.get("display", {}))
        files = [FileSpec(f"runtime/adapters/{name}", "managed", src=f"runtime/adapters/{name}") for name in ADAPTERS]
        inspect = {
            "project_status": CommandSpec("runtime/adapters/inspect_state.py",
                                          '--mode project --workspace "${pluginWorkspace}" --projects ${projectDirs...}'),
            "feature_status": CommandSpec("runtime/adapters/inspect_state.py",
                                          '--mode run --workspace "${pluginWorkspace}" --project "${projectDir}" '
                                          '--feature "${feature}"'),
            "create_project": CommandSpec("runtime/adapters/init_workspace.py",
                                          '--workspace "${pluginWorkspace}" --project "${projectDir}"'),
            "create_feature": CommandSpec("runtime/adapters/init_feature.py",
                                          '--workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" '
                                          '--selected-deployUnit ${selectedDeployUnits}'),
            "dynamic_workflow": CommandSpec("runtime/adapters/inspect_workflow_templates.py"),
            "plugin_dir_hook": CommandSpec(value="${pluginWorkspace}/${projectDir}"),
            "dialog_tips": CommandSpec(value=texts["dialogTips"]),
            "system_prompt_inject": CommandSpec(value=texts["systemPromptInject"]),
        }
        return Contribution(files=files, entries={"knowledge_config": KNOWLEDGE_CONFIG},
                            runtime_config={"board": board_config(ir, options)}, inspect_commands=inspect)
