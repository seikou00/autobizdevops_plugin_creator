#!/usr/bin/env python3
"""DevClaw 的 session_context_inject：生成流程上下文和 agentConfig（interfaces.md §3.3.7）。

会话内容只有流程上下文：演示版没有知识模块，不执行知识组装脚本（interfaces.md §4.5）。
运行策略取“策略目标节点”：当前节点状态的 nextAction.slashSkill 所属节点 → 当前节点 → 全局默认。
除 --selected-deployUnit 不是合法 JSON 数组外，始终返回 ok:true 并以 0 退出，不中断会话。
"""

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.adapters import board_view  # noqa: E402
from runtime.common import query  # noqa: E402
from runtime.common.cli import emit  # noqa: E402


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
    """返回 (agentConfig, 不存在而被跳过的外挂资源)。agents/ 是可选目录，缺失的文件不下发。"""
    # 编译后的 session.json 已由 build 按 Schema 补全 policies.default（含 agentMode），这里不再保留默认值
    policies = query.load_session()["policies"]
    policy = deep_merge(policies["default"], policies.get("nodes", {}).get(node_id or ""))
    subagents = policy.get("subagentConfig", {})
    separator = "\\" if (platform or sys.platform) == "win32" else "/"
    declared = subagents.get("customSubagentFiles", [])
    missing = [path for path in declared if not (query.ROOT / path).is_file()]
    files = [str(query.ROOT / path).replace("/", separator).replace("\\", separator)
             for path in declared if path not in missing]
    return {"agentMode": policy["agentMode"],
            "subagentConfig": {"disabledBuiltinSubagents": list(subagents.get("disabledBuiltinSubagents", [])),
                               "customSubagentFiles": files}}, missing


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
        lines.append(f"- 推进状态：开始时推进到 {target['checkpoints'][0]}，必需产物写好后推进到 {target['checkpoints'][1]}，"
                     "命令见技能正文的“技能状态维护”。")
    flow = {"featureDir": str(directory), "currentNodeId": current["id"] if current else "unknown",
            "currentNodeStatus": status or "unknown", "targetNodeId": target["id"],
            "nextNodeId": following["id"] if following else None, "skill": target["skill"],
            "inputs": input_entries, "outputs": output_entries}
    return "\n".join(lines), flow, target


def render(args):
    result = {"ok": True, "message": "", "sessionContext": "", "agentmdLoadStatus": []}
    try:
        parse_selected(args.selected)
    except ValueError as error:
        result.update(ok=False, message=str(error))
    target = None
    try:
        project_path = query.resolve_project(args.plugin_workspace or None, args.project or None)
        feature = query.resolve_feature(args.feature or None)
        text, flow, target = flow_context(project_path, feature, args.node_id)
        messages = [result["message"]] if result["message"] else []
        messages.append(f"已注入流程上下文（{flow['currentNodeId']}）")
        result.update(message="；".join(messages), sessionContext=text, flow=flow)
    except (query.BoardError, OSError, KeyError) as error:
        result["message"] = "；".join(filter(None, [result["message"], f"未能生成流程上下文: {error}"]))
    result["agentConfig"], missing = agent_config(target["id"] if target else None, args.platform)
    if missing:
        result["message"] = "；".join(filter(None, [result["message"], f"外挂资源不存在，已跳过: {'、'.join(missing)}"]))
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
