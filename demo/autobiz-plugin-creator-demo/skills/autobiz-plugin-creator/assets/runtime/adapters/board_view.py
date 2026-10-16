"""把内部状态转换成看板接口数据（interfaces.md §3.3.3、§3.3.4），展示字段取自 board_config.json。"""

import copy

from runtime.common import query

UNKNOWN_LABEL = "未知"


def board_nodes():
    return query.load_board()["workflow"]["nodes"]


def status_label(node, status):
    if status == "unknown":
        return UNKNOWN_LABEL
    return next(state["label"] for state in node["states"] if state["nodeStatus"] == status)


def workflow_shell():
    nodes = []
    for node in board_nodes():
        clean = {key: copy.deepcopy(node[key]) for key in ("id", "label", "group", "description", "states")}
        if "runtimePolicy" in node:
            clean["runtimePolicy"] = copy.deepcopy(node["runtimePolicy"])
        for state in clean["states"]:
            state["id"] = state["nodeStatus"]
        clean["artifactDefinitions"] = [{key: artifact[key] for key in ("id", "artifactType", "required")}
                                        for artifact in node["artifacts"]["outputs"]]
        nodes.append(clean)
    return {"nodes": nodes}


def relative(project_path, path):
    return path.relative_to(project_path).as_posix()


def artifact_entry(project_path, feature, definition):
    flow_artifact = query.load_flow()["artifacts"][definition["id"]]
    presence = query.artifact_presence(project_path, feature, definition["id"])
    directory = relative(project_path, query.feature_dir(project_path, feature))
    entry = {"id": definition["id"], "artifactLabel": definition["label"],
             "artifactStatus": "generated" if presence["exists"] else "missing",
             "artifactStatusLabel": "已生成" if presence["exists"] else "未生成"}
    patterns = flow_artifact["paths"]
    if len(patterns) == 1 and not any(token in patterns[0] for token in query.GLOB_TOKENS):
        entry["path"] = relative(project_path, presence["files"][0]) if presence["files"] else f"{directory}/{patterns[0]}"
    else:
        entry["paths"] = [relative(project_path, path) for path in presence["files"]] + \
                         [f"{directory}/{pattern}" for pattern in presence["missing"]]
    return entry


def node_statuses(record):
    """当前节点之前为 done，当前节点为 in_progress 或 done，之后为 not_started；Feature 不存在时为 unknown。"""
    nodes = board_nodes()
    if record is None:
        return -1, None, "unknown", ["not_started"] * len(nodes)
    index, node, status = query.locate(record["checkpoint"])
    statuses = ["done" if i < index else status if i == index else "not_started" for i in range(len(nodes))]
    return index, node, status, statuses


def run_payload(project_path, feature):
    record = query.feature_record(project_path, feature)
    index, current, status, statuses = node_statuses(record)
    nodes = board_nodes()
    directory = relative(project_path, query.feature_dir(project_path, feature))
    current_board = nodes[index] if index >= 0 else None
    return {"workflow": workflow_shell(), "run": {
        "featureId": feature, "featureName": feature, "workflowId": "base",
        "workflowProfile": (record or {}).get("workflowProfile", "standard"),
        "workflowTemplate": (record or {}).get("workflowTemplate", "standard"), "workflowDecisions": {},
        "currentNodeId": current["id"] if current else "unknown",
        "currentNodeStatus": status,
        "currentNodeStatusLabel": status_label(current_board, status) if current_board else UNKNOWN_LABEL,
        "nodes": [{"id": node["id"], "nodeStatus": node_status, "nodeStatusLabel": status_label(node, node_status),
                   "artifacts": [artifact_entry(project_path, feature, item) for item in node["artifacts"]["outputs"]]}
                  for node, node_status in zip(nodes, statuses)],
        "hookLogRefs": [{"id": "default", "path": f"{directory}/hooks.ndjson", "format": "ndjson"}],
        "watchRefs": [{"path": relative(project_path, query.state_path(project_path)), "purpose": "run-state"},
                      {"path": directory, "purpose": "artifacts"},
                      {"path": f"{directory}/hooks.ndjson", "purpose": "hook-log"}],
    }}


def project_runs(project_path):
    payload = query.load_state(project_path)
    nodes = board_nodes()
    runs = []
    for feature in sorted(payload["features"]):
        index, _, status, _ = node_statuses(payload["features"][feature])
        runs.append({"featureId": feature, "featureName": feature, "currentNodeId": nodes[index]["id"],
                     "currentNodeStatus": status, "currentNodeStatusLabel": status_label(nodes[index], status),
                     "nodeIds": [node["id"] for node in nodes]})
    return {"runs": runs}
