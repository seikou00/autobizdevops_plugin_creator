#!/usr/bin/env python3
"""DevClaw 的 session_context_inject：生成流程上下文和 agentConfig（interfaces.md §3.3.7）。

会话内容依次为：流程上下文（始终生成）、自定义会话入口的输出（声明了 session.customEntry 时）。
运行策略取“策略目标节点”：当前节点状态的 nextAction.slashSkill 所属节点 → 当前节点 → 全局默认。
除 --selected-deployUnit 不是合法 JSON 数组外，始终返回 ok:true 并以 0 退出，不中断会话。
"""

import argparse
import copy
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.adapters import board_view  # noqa: E402
from runtime.common import query  # noqa: E402
from runtime.common.cli import emit  # noqa: E402

BUILTIN_POLICY = {"agentMode": "solo", "toolCustomConfig": {"task": {"enabled": True}}}


def deep_merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        merged[key] = deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) \
            else copy.deepcopy(value)
    return merged


def parse_selected(raw):
    if not raw or not raw.strip():
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"--selected-deployUnit 不是合法 JSON: {error}")
    if not isinstance(value, list):
        raise ValueError("--selected-deployUnit 必须是 JSON 数组")
    return value


def agent_config(node_id, platform):
    policies = query.load_session().get("policies", {})
    policy = deep_merge(deep_merge(BUILTIN_POLICY, policies.get("default")), policies.get("nodes", {}).get(node_id or ""))
    subagents = policy.get("subagentConfig", {})
    separator = "\\" if (platform or sys.platform) == "win32" else "/"
    files = [str(query.ROOT / path).replace("/", separator).replace("\\", separator)
             for path in subagents.get("customSubagentFiles", [])]
    return {"agentMode": policy.get("agentMode", "solo"),
            "toolConfig": {"task": {"enabled": policy.get("toolCustomConfig", {}).get("task", {}).get("enabled", True)}},
            "subagentConfig": {"disabledBuiltinSubagents": list(subagents.get("disabledBuiltinSubagents", [])),
                               "customSubagentFiles": files}}


def target_node(record, node_id):
    """返回 (当前节点, 当前状态, 策略目标节点)。"""
    if node_id:
        node = query.node_by_id(node_id)
        return node, None, node
    if record is None:
        return None, None, None
    _, current, status = query.locate(record["checkpoint"])
    board_node = next(node for node in board_view.board_nodes() if node["id"] == current["id"])
    action = next(state["nextAction"] for state in board_node["states"] if state["nodeStatus"] == status)
    target = query.node_by_skill(action.get("slashSkill", "")) if action.get("slashSkill") else None
    return current, status, target or current


def describe(project_path, feature, artifacts):
    rows, entries = [], []
    for artifact in artifacts:
        presence = query.artifact_presence(project_path, feature, artifact["id"])
        entries.append({"id": artifact["id"], "required": True, "exists": presence["exists"]})
        rows.append(f"{artifact['label']}（{'、'.join(artifact['paths'])}，{'已存在' if presence['exists'] else '未生成'}）")
    return rows, entries


def flow_context(project_path, feature, node_id):
    record = query.feature_record(project_path, feature)
    current, status, target = target_node(record, node_id)
    directory = query.feature_dir(project_path, feature)
    if target is None:
        text = f"## 当前流程\n- Feature {feature} 尚未创建，请先在看板上创建 Feature。"
        return text, {"featureDir": str(directory), "currentNodeId": "unknown", "currentNodeStatus": "unknown"}, None
    following = query.next_node(target["id"])
    finished = current is not None and status == "done" and following is None and target["id"] == current["id"]
    inputs, input_entries = describe(project_path, feature, query.node_artifacts(target["id"], "inputs"))
    outputs, output_entries = describe(project_path, feature, query.node_artifacts(target["id"], "outputs"))
    templates = [str(path) for path in query.node_templates(target["id"])]
    status_text = {"in_progress": "进行中", "done": "已完成"}.get(status, "调试指定")
    lines = ["## 当前流程", f"- Feature：{feature}", f"- 产物目录 FEATURE_DIR：{directory}"]
    if current is not None:
        lines.append(f"- 当前节点：{current['name']}（{current['id']}），{status_text}")
    if finished:
        lines.append("- 流程已全部完成。只查看成果；用户明确要求修改时才重开对应阶段。")
    else:
        lines += [f"- 接下来：使用技能 /{target['skill']} 处理「{target['name']}」",
                  f"- 需要读取：{'；'.join(inputs) or '无'}",
                  f"- 需要产出：{'；'.join(outputs) or '无'}"]
        if templates:
            lines.append(f"- 可用模板：{'；'.join(templates)}")
        lines.append(f"- 推进状态：开始时推进到 {target['checkpoints'][0]}，必需产物写好后推进到 {target['checkpoints'][1]}，"
                     "命令见技能正文的“技能状态维护”。")
    flow = {"featureDir": str(directory), "currentNodeId": current["id"] if current else "unknown",
            "currentNodeStatus": status or "unknown", "targetNodeId": target["id"],
            "nextNodeId": following["id"] if following else None, "skill": target["skill"],
            "inputs": input_entries, "outputs": output_entries, "templates": templates}
    return "\n".join(lines), flow, target


def custom_entry(request, target, project_path, feature):
    """执行开发者声明的自定义会话入口（interfaces.md §4.5），返回 (sessionContext, message, 失败原因)。"""
    entry = query.load_session().get("customEntry")
    if not entry:
        return "", "", ""
    values = {"python": sys.executable, "pluginPath": str(query.ROOT),
              "skillPath": str(query.ROOT / "skills" / target["skill"]) if target else "",
              "projectPath": str(project_path), "featureDir": request.get("featureDir", ""),
              "feature": feature or "", "nodeId": target["id"] if target else ""}
    try:
        args = []
        for arg in shlex.split(entry["command"]):
            for name, value in values.items():
                arg = arg.replace("${" + name + "}", value)
            args.append(arg)
        completed = subprocess.run(args, cwd=query.ROOT, input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=entry.get("timeoutSec", 30))
        if completed.returncode != 0:
            return "", "", f"退出码 {completed.returncode}"
        output = json.loads(completed.stdout.decode("utf-8"))
        if not isinstance(output, dict):
            return "", "", "输出不是 JSON 对象"
        return str(output.get("sessionContext", "")), str(output.get("message", "")), ""
    except subprocess.TimeoutExpired:
        return "", "", "超时"
    except (OSError, ValueError) as error:
        return "", "", str(error)


def render(args):
    result = {"ok": True, "message": "", "sessionContext": "", "agentmdLoadStatus": []}
    try:
        selected = parse_selected(args.selected)
    except ValueError as error:
        result.update(ok=False, message=str(error))
        selected = []
    target = None
    try:
        project_path = query.resolve_project(args.plugin_workspace or None, args.project or None)
        feature = query.resolve_feature(args.feature or None)
        text, flow, target = flow_context(project_path, feature, args.node_id)
        parts = [text]
        request = {"schema": "autobiz.session.request.v1", "platform": args.platform or sys.platform,
                   "pluginRoot": str(query.ROOT), "pluginWorkspace": str(project_path.parent),
                   "project": project_path.name, "feature": feature, "featureDir": flow["featureDir"],
                   "selectedDeployUnits": selected, "sessionWorkspacePath": args.session_workspace_path,
                   "knowledgePath": args.knowledge_path or "", "flow": flow,
                   "agentConfig": agent_config(target["id"] if target else None, args.platform)}
        extra, extra_message, failure = custom_entry(request, target, project_path, feature)
        if extra.strip():
            parts.append(extra.strip())
        messages = [result["message"]] if result["message"] else []
        messages.append(f"已注入流程上下文（{flow['currentNodeId']}）")
        if extra_message:
            messages.append(extra_message)
        if failure:
            messages.append(f"自定义会话入口失败: {failure}")
        result.update(message="；".join(messages), sessionContext="\n\n".join(parts), flow=flow)
    except (query.BoardError, OSError, KeyError) as error:
        result["message"] = "；".join(filter(None, [result["message"], f"未能生成流程上下文: {error}"]))
    result["agentConfig"] = agent_config(target["id"] if target else None, args.platform)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=["darwin", "linux", "win32"])
    parser.add_argument("--plugin-workspace", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--feature", default="")
    parser.add_argument("--selected-deployUnit", dest="selected", default="")
    parser.add_argument("--session-workspace-path", default="")
    parser.add_argument("--knowledge-path", default="", help="本地调试用；演示版没有知识模块，忽略")
    parser.add_argument("--node-id", default="", help="本地调试：直接指定策略目标节点")
    args = parser.parse_args()
    emit(render(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
