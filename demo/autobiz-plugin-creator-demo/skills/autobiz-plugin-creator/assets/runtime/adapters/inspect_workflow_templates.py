#!/usr/bin/env python3
"""DevClaw 的 dynamic_workflow：返回模板与节点定义，只读（interfaces.md §3.3.5）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.common import query  # noqa: E402
from runtime.common.cli import execute  # noqa: E402


def templates():
    workflow = query.load_board()["workflow"]
    nodes = workflow["nodes"]
    return {"ok": True, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
            "templates": [{"id": key, "templateType": "classical", "label": value["label"],
                           "description": value["description"], "nodes": [node["id"] for node in nodes]}
                          for key, value in workflow["templates"].items()],
            "nodes": [{"id": node["id"], "label": node["label"], "group": node["group"], "skill": node["skill"],
                       "description": node["description"], **node["artifacts"]} for node in nodes]}


if __name__ == "__main__":
    sys.exit(execute(templates))
