"""看板数据拼装（interfaces.md §3.3.3–§3.3.5，input-config.md §6）。

读取命令和看板事件共用这一套代码，保证推送内容与读取命令的输出一致（D59）。
"""

from __future__ import annotations

import copy

from runtime.common import query

UNKNOWN_LABEL = "未知"
GENERATED, MISSING = ("generated", "已生成"), ("missing", "未生成")


def _board_node(node_id: str) -> dict:
    for group in query.load_board().get("nodes", {}).values():
        for item in group:
            if item["id"] == node_id:
                return item
    return {"id": node_id, "description": "", "nextAction": {}}


def state_label(status: str) -> str:
    if status == "unknown":
        return UNKNOWN_LABEL
    return query.load_board().get("stateLabels", {}).get(status, status)


def node_statuses(node: dict) -> tuple:
    return ("not_started", "archived") if node.get("terminal") else ("not_started", "in_progress", "done")


def runtime_policy(node_id: str):
    for group in query.load_session().get("policies", {}).get("nodes", {}).values():
        for item in group:
            if item.get("id") == node_id:
                return {key: copy.deepcopy(value) for key, value in item.items() if key != "id"}
    return None


def next_action(node_id: str, status: str) -> dict:
    return copy.deepcopy(_board_node(node_id).get("nextAction", {}).get(status, {}))


def artifact_def(ref: dict) -> dict:
    result = {"id": ref["id"], "label": ref["label"], "artifactType": ref["type"], "path": ref["paths"][0],
              "required": ref["required"]}
    if len(ref["paths"]) > 1:
        result["paths"] = list(ref["paths"])
    return result


def workflow_node(node: dict) -> dict:
    result = {"id": node["id"], "label": node["name"], "group": node["stage"], "order": node["order"],
              "skill": node["skill"], "description": _board_node(node["id"]).get("description", "")}
    policy = runtime_policy(node["id"])
    if policy is not None:
        result["runtimePolicy"] = policy
    result["checkpoints"] = list(node["checkpoints"])
    result["states"] = [{"nodeStatus": status, "id": status, "label": state_label(status),
                         "nextAction": next_action(node["id"], status)} for status in node_statuses(node)]
    result["artifacts"] = {direction: [artifact_def(ref) for ref in query.node_artifacts(node["id"], direction)]
                           for direction in ("inputs", "outputs")}
    return result


def workflow_payload() -> dict:
    return {"nodes": [workflow_node(node) for node in query.nodes()], "dynamicStages": []}


def statuses(record) -> list:
    """按流程顺序给出每个节点的状态；Feature 不存在时全部为 not_started。"""
    nodes = query.nodes()
    if record is None or query.is_stranded(record):
        return ["not_started"] * len(nodes)
    index, _, status = query.locate(record["checkpoint"])
    return ["done" if i < index else status if i == index else "not_started" for i in range(len(nodes))]


def _relative(project_path, path) -> str:
    return query.relative_to_project(project_path, path)


def artifact_entry(project_path, feature: str, ref: dict) -> dict:
    presence = query.artifact_presence(project_path, feature, ref["id"])
    status, label = GENERATED if presence["exists"] else MISSING
    entry = {"id": ref["id"], "artifactLabel": ref["label"], "artifactStatus": status, "artifactStatusLabel": label}
    directory = _relative(project_path, query.feature_dir(project_path, feature))
    patterns = ref["paths"]
    if len(patterns) == 1 and not any(char in patterns[0] for char in query.GLOB_CHARS):
        found = presence["files"] + presence["empty"]
        entry["path"] = _relative(project_path, found[0]) if found else f"{directory}/{patterns[0]}"
    else:
        matched = sorted(presence["files"] + presence["empty"])
        entry["paths"] = [_relative(project_path, path) for path in matched] + \
                         [f"{directory}/{pattern}" for pattern in presence["missing"]]
    return entry


def run_payload(project_path, feature: str) -> dict:
    record = query.feature_record(project_path, feature)
    nodes = query.nodes()
    states = statuses(record)
    if record is None or query.is_stranded(record):
        current_id, current_status = "unknown", "unknown"
    else:
        current, current_status = query.current_node(record)
        current_id = current["id"]
    metadata = _relative(project_path, query.metadata_dir(project_path)) if query.metadata_dir(project_path) != \
        project_path else "."
    hook_log = f"{metadata}/hooks.ndjson"
    return {
        "featureId": feature, "featureName": feature, "workflowId": "base",
        "workflowProfile": (record or {}).get("workflowProfile", "standard"),
        "workflowTemplate": (record or {}).get("workflowTemplate", "standard"),
        "workflowDecisions": {}, "workflowSkippedNodes": [], "pendingChoice": None,
        "currentNodeId": current_id, "currentNodeStatus": current_status,
        "currentNodeStatusLabel": state_label(current_status),
        "nodes": [{"id": node["id"], "nodeStatus": status, "nodeStatusLabel": state_label(status),
                   "artifacts": [artifact_entry(project_path, feature, ref)
                                 for ref in query.node_artifacts(node["id"], "outputs")]}
                  for node, status in zip(nodes, states)],
        "hookLogRefs": [{"id": "default", "path": hook_log, "format": "ndjson"}],
        "watchRefs": [{"path": f"{metadata}/state.json", "purpose": "run-state"},
                      {"path": f"{metadata}/features/{feature}", "purpose": "artifacts"},
                      {"path": hook_log, "purpose": "hook-log"}],
        **({"readOnly": True, "readOnlyReason": query.stranded_reason(record)}
           if record is not None and query.is_stranded(record) else {}),
    }


def project_runs(project_path) -> dict:
    runs = []
    node_ids = [node["id"] for node in query.active_nodes()]
    for record in query.list_features(project_path):
        if query.is_stranded(record):
            runs.append({"featureId": record["feature"], "featureName": record["feature"], "currentNodeId": "unknown",
                         "currentNodeStatus": "unknown", "currentNodeStatusLabel": state_label("unknown"),
                         "nodeIds": node_ids, "readOnly": True, "readOnlyReason": query.stranded_reason(record)})
            continue
        current, status = query.current_node(record)
        runs.append({"featureId": record["feature"], "featureName": record["feature"], "currentNodeId": current["id"],
                     "currentNodeStatus": status, "currentNodeStatusLabel": state_label(status), "nodeIds": node_ids})
    return {"runs": runs}


def checkpoint_contract() -> dict:
    flow = query.load_flow()
    chain = flow["checkpoints"]["chain"]
    return {"initial": [flow["checkpoints"]["initial"]],
            "transitions": {checkpoint: chain[index + 1:index + 2] for index, checkpoint in enumerate(chain)},
            "stageLabels": dict(flow["checkpoints"]["labels"])}


def node_transitions() -> list:
    nodes = query.nodes()
    result = []
    for current, following in zip(nodes, nodes[1:]):
        target_state = "archived" if following.get("terminal") else "in_progress"
        result.append({"id": f"{current['id']}-to-{following['id']}",
                       "from": {"nodeId": current["id"], "state": "done"},
                       "to": {"nodeId": following["id"], "state": target_state}})
    return result


def templates_payload() -> dict:
    board = query.load_board()
    template = board.get("template", {})
    return {
        "ok": True, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
        "templates": [{"id": "standard", "templateType": "classical", "label": template.get("label", ""),
                       "description": template.get("description", ""),
                       "nodes": [node["id"] for node in query.nodes()]}],
        "nodes": [{"id": node["id"], "label": node["name"], "group": node["stage"], "skill": node["skill"],
                   "description": _board_node(node["id"]).get("description", ""),
                   "inputs": [artifact_def(ref) for ref in query.node_artifacts(node["id"], "inputs")],
                   "outputs": [artifact_def(ref) for ref in query.node_artifacts(node["id"], "outputs")]}
                  for node in query.nodes()],
        "checkpoints": checkpoint_contract(),
        "transitions": node_transitions(),
    }
