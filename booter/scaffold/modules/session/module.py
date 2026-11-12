"""运行策略模块：校验并编译全局和逐节点策略。"""

from __future__ import annotations

from scaffold.build.contribute import Contribution
from scaffold.lib import derive
from scaffold.lib.issues import error, warning
from scaffold.modules import Module

FILE = "modules/session.json"


def policies(options: dict) -> dict:
    source = options.get("policies", {})
    return {"default": source.get("default", {}), "nodes": source.get("nodes", {})}


class SessionModule(Module):
    def validate(self, ir, options, ctx):
        issues = []
        groups = {node.id: node.group for node in ir.nodes}
        nodes = policies(options)["nodes"]
        seen = set()
        for group in derive.GROUPS:
            for index, item in enumerate(nodes.get(group) or []):
                pointer = f"/policies/nodes/{group}/{index}"
                node_id = item.get("id")
                if node_id not in groups:
                    issues.append(error("POLICY_NODE_UNKNOWN", f"节点策略的 id {node_id} 不是 workflow.json 中的节点",
                                        file=FILE, pointer=f"{pointer}/id"))
                elif groups[node_id] != group:
                    issues.append(error("POLICY_NODE_UNKNOWN",
                                        f"节点 {node_id} 在 workflow.json 的 {groups[node_id]} 分组中，不在 {group} 分组中",
                                        file=FILE, pointer=f"{pointer}/id",
                                        hint=f"把这一项移到 policies.nodes.{groups[node_id]}"))
                elif node_id in seen:
                    issues.append(error("POLICY_NODE_UNKNOWN", f"节点 {node_id} 的策略出现了多次", file=FILE,
                                        pointer=f"{pointer}/id"))
                seen.add(node_id)
        entries = [("/policies/default", policies(options)["default"])]
        entries += [(f"/policies/nodes/{group}/{index}", item) for group in derive.GROUPS
                    for index, item in enumerate(nodes.get(group) or [])]
        for pointer, policy in entries:
            files = (policy.get("subagentConfig") or {}).get("customSubagentFiles") or []
            for index, path in enumerate(files):
                if not ctx.tree.is_file(path):
                    issues.append(warning("SUBAGENT_FILE_MISSING", f"外挂资源 {path} 不存在，会话入口下发 agentConfig 时会跳过它",
                                          file=FILE, pointer=f"{pointer}/subagentConfig/customSubagentFiles/{index}"))
        return issues

    def contribute(self, ir, options, ctx):
        config = {"schema": "autobiz.session.v1", "policies": policies(options)}
        return Contribution(runtime_config={"session": config})
