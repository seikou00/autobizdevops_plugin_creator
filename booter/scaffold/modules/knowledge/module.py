"""知识模块：清单解析、内置知识组装与可选的知识仓库同步（input-config.md §4.3、output-spec.md §7.1，D53）。"""

from __future__ import annotations

from scaffold.build.contribute import CommandSpec, Contribution, FileSpec
from scaffold.modules import Module

ROOT = "sys"
ASSEMBLER = "runtime/knowledge/render_collected_session_context.py"
KNOWLEDGE_ARGS = '--knowledge-path "${pluginPath}/sys" --knowledge-path-platform "${knowledge-path}"'


def knowledge_config(options: dict) -> dict:
    manifest = options.get("manifest", {})
    assembly = options.get("assembly", {})
    source = options.get("source")
    return {
        "schema": "autobiz.knowledge.v1",
        "root": ROOT,
        "manifest": {"format": manifest.get("format"), "path": manifest.get("path")},
        "assembly": {"enabled": assembly.get("enabled"), "assembler": assembly.get("assembler"),
                     "timeoutSec": assembly.get("timeoutSec")},
        "source": None if source is None else {"type": source.get("type"), "url": source.get("url"),
                                               "sshUrl": source.get("sshUrl"), "ref": source.get("ref")},
    }


class KnowledgeModule(Module):
    def contribute(self, ir, options, ctx):
        assembly = options.get("assembly", {})
        plugin_assembles = assembly.get("assembler") == "plugin"
        source = options.get("source") is not None

        def module_file(name, **extra):
            return FileSpec(f"runtime/knowledge/{name}", "module", src=f"files/{name}", **extra)

        files = [module_file("__init__.py"), module_file("inspect_deploy_units.py")]
        if plugin_assembles:
            files += [module_file("render_collected_session_context.py", replaceable=True),
                      module_file("collect-knowledge.js")]
        if source:
            files.append(module_file("sync_knowledge.py"))
        commands = {
            "knowledge_path": CommandSpec(value="${pluginPath}/sys"),
            "deploy_units": CommandSpec("runtime/knowledge/inspect_deploy_units.py", KNOWLEDGE_ARGS),
        }
        if source:
            commands["pull_knowledge"] = CommandSpec("runtime/knowledge/sync_knowledge.py")
        knowledge_assembly = None
        if plugin_assembles and assembly.get("enabled", True):
            knowledge_assembly = {"script": ASSEMBLER, "timeoutSec": assembly.get("timeoutSec")}
        return Contribution(files=files, manifest={"assembler": assembly.get("assembler"), "source": source},
                            runtime_config={"knowledge": knowledge_config(options)}, inspect_commands=commands,
                            knowledge_assembly=knowledge_assembly)
