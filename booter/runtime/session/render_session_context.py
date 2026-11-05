"""默认会话入口 session_context_inject（interfaces.md §3.3.7）。

按顺序拼装：流程上下文（始终生成）→ 知识组装结果（知识模块启用且 assembler = plugin）。
运行策略按“nextAction 目标节点 → 当前节点 → 全局默认”三级降级，映射为 agentConfig。
始终以 0 退出，用 ok 字段表示结果；只读，不创建或修改任何文件。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import copy  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402

from runtime.adapters import board_view  # noqa: E402
from runtime.common import cli, query  # noqa: E402

REQUEST_SCHEMA = "autobiz.session.request.v1"


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def parse_units(raw):
    """返回 (发布单元列表, 错误)；只有不是合法 JSON 数组时才是错误。"""
    if raw is None or not raw.strip():
        return [], None
    try:
        units = json.loads(raw)
    except ValueError as error:
        return [], f"--selected-deployUnit 不是合法的 JSON 数组: {error}"
    if not isinstance(units, list):
        return [], "--selected-deployUnit 必须是 JSON 数组"
    return [unit for unit in units if isinstance(unit, dict)], None


def target_node(record, explicit: str = None):
    """策略目标节点：与宿主拉起技能时依据的 nextAction 保持一致。"""
    if explicit:
        return query.node(explicit)
    if record is None:
        return None
    current, status = query.current_node(record)
    skill = board_view.next_action(current["id"], status).get("slashSkill")
    return (query.node_by_skill(skill) if skill else None) or current


def agent_config(node, platform: str, messages: list) -> dict:
    policies = query.load_session().get("policies", {})
    policy = copy.deepcopy(policies.get("default", {}))
    if node is not None:
        policy = deep_merge(policy, board_view.runtime_policy(node["id"]) or {})
    sub = policy.get("subagentConfig") or {}
    files = []
    for rel in sub.get("customSubagentFiles") or []:
        path = ROOT / rel
        if not path.is_file():
            messages.append(f"外挂资源不存在，已跳过: {rel}")
            continue
        text = str(path.resolve())
        files.append(text.replace("/", "\\") if platform == "win32" else text.replace("\\", "/"))
    result = {"agentMode": policy.get("agentMode", "multi"),
              "subagentConfig": {"disabledBuiltinSubagents": list(sub.get("disabledBuiltinSubagents") or []),
                                 "customSubagentFiles": files}}
    if "toolCustomConfig" in policy:
        result["toolCustomConfig"] = copy.deepcopy(policy["toolCustomConfig"])
    return result


def artifact_states(project, feature, record, node_id, direction):
    result = []
    for ref in query.node_artifacts(node_id, direction):
        exists = record is not None and query.artifact_presence(project, feature, ref["id"])["exists"]
        result.append({"id": ref["id"], "label": ref["label"], "required": ref["required"], "exists": exists})
    return result


def flow_context(project, feature, record, target) -> dict:
    flow = {"featureDir": str(query.feature_dir(project, feature)) if project is not None and feature else "",
            "currentNodeId": "unknown", "currentNodeStatus": "unknown",
            "targetNodeId": target["id"] if target else None, "nextNodeId": None,
            "skill": target["skill"] if target else None, "inputs": [], "outputs": [], "pendingChoice": None}
    if record is not None:
        current, status = query.current_node(record)
        flow.update(currentNodeId=current["id"], currentNodeStatus=status)
    if target is not None:
        following = query.next_node(target["id"], record)
        flow["nextNodeId"] = following["id"] if following else None
        flow["inputs"] = artifact_states(project, feature, record, target["id"], "inputs")
        flow["outputs"] = artifact_states(project, feature, record, target["id"], "outputs")
    return flow


def _artifact_line(item) -> str:
    need = "必需" if item["required"] else "可选"
    have = "已生成" if item["exists"] else "未生成"
    return f"`{item['label']}`（{need}，{have}）"


def render_flow(feature, flow) -> str:
    lines = ["## 当前流程"]
    if flow["currentNodeId"] == "unknown":
        lines.append(f"- Feature `{feature or ''}` 尚未创建，看板上创建 Feature 后再开始。")
        return "\n".join(lines)
    current = query.node(flow["currentNodeId"])
    lines.append(f"- Feature：`{feature}`；产物目录 FEATURE_DIR=`{flow['featureDir']}`")
    lines.append(f"- 当前节点：{current['name']}（`{current['id']}`），状态：{board_view.state_label(flow['currentNodeStatus'])}")
    if flow["targetNodeId"]:
        target = query.node(flow["targetNodeId"])
        lines.append(f"- 本次会话对应节点：{target['name']}（`{target['id']}`），技能 `/{target['skill']}`")
        if flow["inputs"]:
            lines.append("- 输入：" + "、".join(_artifact_line(item) for item in flow["inputs"]))
        if flow["outputs"]:
            lines.append("- 输出（写在 FEATURE_DIR 下）：" + "、".join(_artifact_line(item) for item in flow["outputs"]))
        if flow["nextNodeId"]:
            following = query.node(flow["nextNodeId"])
            lines.append(f"- 下一节点：{following['name']}（`{following['id']}`）")
        else:
            lines.append("- 下一节点：无，这是流程的最后一个节点")
    lines.append("- 状态只按技能 SKILL.md 开头“技能状态维护”中的命令推进，不要直接修改 state.json。")
    return "\n".join(lines)


def assemble_knowledge(args, project, feature, units, flow, config, messages):
    assembly = query.load_session().get("knowledgeAssembly")
    if not assembly:
        return "", []
    from runtime.knowledge.inspect_deploy_units import choose_knowledge_dir

    unit_ids = [unit["deployUnitId"] for unit in units if isinstance(unit.get("deployUnitId"), str)]
    knowledge_path = str(choose_knowledge_dir(args.knowledge_path, args.knowledge_path_platform, unit_ids))
    request = {"schema": REQUEST_SCHEMA, "platform": args.platform, "pluginRoot": str(ROOT),
               "pluginWorkspace": args.plugin_workspace or "", "project": args.project or "", "feature": feature or "",
               "featureDir": flow["featureDir"], "selectedDeployUnits": units,
               "sessionWorkspacePath": args.session_workspace_path or "",
               "knowledgePath": str(Path(knowledge_path).resolve()) if knowledge_path else "",
               "flow": flow, "agentConfig": config}
    script = ROOT / assembly["script"]
    try:
        completed = subprocess.run([sys.executable, "-X", "utf8", str(script)], cwd=str(ROOT),
                                   input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=assembly.get("timeoutSec") or 30)
    except subprocess.TimeoutExpired:
        messages.append("知识组装失败: 超时")
        return "", []
    except OSError as error:
        messages.append(f"知识组装失败: {error}")
        return "", []
    if completed.stderr:
        sys.stderr.write(completed.stderr.decode("utf-8", "replace"))
    if completed.returncode != 0:
        messages.append(f"知识组装失败: 退出码 {completed.returncode}")
        return "", []
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except ValueError:
        messages.append("知识组装失败: 输出不是合法 JSON")
        return "", []
    if not isinstance(payload, dict):
        messages.append("知识组装失败: 输出不是 JSON 对象")
        return "", []
    if payload.get("message"):
        messages.append(str(payload["message"]))
    status = payload.get("agentmdLoadStatus")
    return str(payload.get("sessionContext") or ""), status if isinstance(status, list) else []


def render(args) -> dict:
    messages = []
    units, unit_error = parse_units(args.selected_deploy_unit)
    feature = args.feature or None
    project = record = None
    try:
        project = query.resolve_project(args.plugin_workspace, args.project)
        if feature:
            record = query.feature_record(project, feature)
        if record is not None and query.is_stranded(record):
            messages.append(query.stranded_reason(record))
            record = None
    except query.BoardError as error:
        messages.append(str(error))
    if record is not None and units:
        recorded = [unit.get("deployUnitId") for unit in record.get("deployUnits", [])]
        selected = [unit.get("deployUnitId") for unit in units]
        if recorded and recorded != selected:
            messages.append("所选发布单元与创建 Feature 时记录的不一致：" + "、".join(map(str, selected)))
    target = target_node(record, args.node_id)
    config = agent_config(target, args.platform, messages)
    flow = flow_context(project, feature, record, target)
    knowledge, load_status = assemble_knowledge(args, project, feature, units, flow, config, messages)
    if unit_error:
        messages.insert(0, unit_error)
    sections = [render_flow(feature, flow), knowledge]
    return {"ok": unit_error is None, "message": "；".join(messages),
            "sessionContext": "\n\n".join(section for section in sections if section.strip()),
            "agentmdLoadStatus": load_status, "flow": flow, "agentConfig": config}


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="生成会话内容（session_context_inject）")
    parser.add_argument("--platform", default=sys.platform if sys.platform in ("darwin", "win32") else "linux")
    parser.add_argument("--plugin-workspace")
    parser.add_argument("--project")
    parser.add_argument("--feature")
    parser.add_argument("--selected-deployUnit", dest="selected_deploy_unit")
    parser.add_argument("--session-workspace-path")
    parser.add_argument("--knowledge-path")
    parser.add_argument("--knowledge-path-platform")
    parser.add_argument("--node-id")
    return cli.run(lambda: render(parser.parse_args(argv)), always_zero=True)


if __name__ == "__main__":
    sys.exit(main())
