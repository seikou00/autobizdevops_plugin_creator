"""会话模块（core）：默认会话入口与运行策略 session.json（input-config.md §4.2，interfaces.md §3.3.7）。"""

from __future__ import annotations

from scaffold.build.contribute import CommandSpec, Contribution, FileSpec
from scaffold.lib import derive
from scaffold.lib.issues import error, warning
from scaffold.modules import Module

FILE = "modules/session.json"
SCRIPT = "runtime/session/render_session_context.py"
ARGS = ('--platform {platform} --plugin-workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" '
        '--selected-deployUnit ${selectedDeployUnits} --session-workspace-path "${sessionWorkspacePath}"')
KNOWLEDGE_ARGS = ' --knowledge-path "${pluginPath}/sys" --knowledge-path-platform "${knowledge-path}"'


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
        args = ARGS + (KNOWLEDGE_ARGS if "knowledge" in ctx.enabled else "")
        files = [FileSpec("runtime/session/__init__.py", "managed", src="runtime/session/__init__.py"),
                 FileSpec(SCRIPT, "managed", src=SCRIPT)]
        config = {"schema": "autobiz.session.v1", "policies": policies(options), "knowledgeAssembly": None}
        return Contribution(files=files, runtime_config={"session": config},
                            inspect_commands={"session_collector_context_inject": CommandSpec(SCRIPT, args)})
