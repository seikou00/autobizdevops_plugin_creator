"""不属于任何模块的输出，以及合并后才能生成的 board_core/（scaffold.md 单元 7）。"""

from __future__ import annotations

from scaffold.build.contribute import Contribution, FileSpec
from scaffold.build.load import HOOKS_FILE, MODULE_KEYS, hook_events
from scaffold.lib import fsio

FRAMEWORK_FILES = (
    "runtime/__init__.py",
    "runtime/common/__init__.py", "runtime/common/query.py", "runtime/common/engine.py", "runtime/common/cli.py",
    "runtime/workflow/__init__.py", "runtime/workflow/update_state.py",
    "runtime/adapters/__init__.py", "runtime/adapters/board_view.py", "runtime/adapters/board_events.py",
)
GUARD_SCRIPT = "hooks/artifact_guard.py"   # 模板在 runtime/hooks/，拷到插件根目录的 hooks/
# 默认钩子：执行完成命令前检查必需产物存在且非空，不满足时拦截（与 update_state.py 的检查冗余，D61）
ARTIFACT_GUARD = {
    "matcher": "execute",
    "hooks": [{
        "type": "command",
        "command": f"python -X utf8 {GUARD_SCRIPT}",
        "timeout": 30,
        "onBlock": {"reason": "产物检查不通过", "systemMessage": "必需产物缺失或为空",
                    "additionalContext": "补全必需产物后再执行技能完成命令"},
        "persistAfterInterrupt": True,
    }],
}
SCHEMA_FILES = ("plugin-scaffold.schema.json", "workflow.schema.json", "modules/board.schema.json",
                "modules/session.schema.json", "modules/knowledge.schema.json", "modules/artifactSync.schema.json",
                "modules/globalHooks.schema.json")
PLUGIN_FIELDS = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
API_VERSION = 1
BOARD_EVENTS = {"protocol": "autobiz.board-events.v1"}


def skill_dir(skill_dirs: dict, skill: str) -> str:
    found, _ = skill_dirs.get(skill, (None, []))
    return found or f"skills/{skill}"


def plugin_manifest(plugin: dict) -> dict:
    result = {key: plugin[key] for key in PLUGIN_FIELDS if key in plugin}
    result["skills"] = "./skills/"
    if "mcpServers" in plugin:
        result["mcpServers"] = plugin["mcpServers"]
    result["hooks"] = f"./{HOOKS_FILE}"   # 固定指向 hooks/hooks.json（D61）
    return result


def managed_scripts() -> tuple:
    """命令中出现这些路径的条目归脚手架维护：产物检查钩子、所有全局钩子的目录，以及旧版生成在 runtime/hooks/ 下的脚本。"""
    from scaffold.modules.global_hooks.catalog import catalog

    return (GUARD_SCRIPT, "runtime/hooks/") + tuple(f"{spec.target}/" for spec in catalog().values())


def _is_managed(item: dict, scripts: tuple) -> bool:
    return any(isinstance(hook, dict) and any(script in str(hook.get("command", "")) for script in scripts)
               for hook in item.get("hooks") or [])


def merged_hooks(contributed: dict, existing) -> tuple:
    """返回 (hooks/hooks.json 的内容, 脚手架维护的条目)。

    脚手架的条目（产物检查钩子、globalHooks 启用的钩子）排在每个事件的最前面；文件中现有的其他条目是开发者的，
    按原顺序保留在后面。现有文件中命令指向托管脚本的条目视为脚手架的旧条目，丢弃后重新生成。
    沿用现有文件的写法（是否包在 hooks 下）。"""
    events, wrapped = hook_events(existing) if existing is not None else ({}, False)
    scripts = managed_scripts()
    managed = {event: list(items) for event, items in contributed.items()}
    result = {event: list(items) for event, items in managed.items()}
    for event, items in events.items():
        kept = [item for item in items if not _is_managed(item, scripts)]
        if kept or not items:
            result[event] = result.get(event, []) + kept
    return ({"hooks": result} if wrapped else result), managed


def render_hooks(merged, existing) -> tuple:
    """返回 (路径, 内容, 脚手架条目的摘要)。"""
    content, managed = merged_hooks(merged.hooks, existing)
    return HOOKS_FILE, fsio.dump_json(content), fsio.digest(fsio.dump_json(managed))


def runtime_config(ir) -> dict:
    return {"schema": "autobiz.runtime.v1", "pluginId": ir.plugin["id"], "metaRoot": ir.runtime["metaRoot"],
            "validateTimeoutSec": ir.runtime["validateTimeoutSec"]}


def flow_config(ir, normalized, skill_dirs: dict) -> dict:
    workflow_rel = normalized.inputs.files["workflow"]
    labels = {}
    for node in ir.nodes:
        if node.terminal:
            labels["archived"] = node.id
        else:
            labels[f"{node.id}_in_progress"] = f"{node.name}进行中"
            labels[f"{node.id}_done"] = f"{node.name}完成"
    return {
        "schema": "autobiz.flow.v1",
        "source": {workflow_rel: normalized.inputs.digests[workflow_rel]},
        "stages": list(ir.stages),
        "artifacts": {artifact.id: {"label": artifact.label, "type": artifact.type, "paths": list(artifact.paths),
                                    "producer": artifact.producer} for artifact in ir.artifacts.values()},
        "nodes": [{
            "id": node.id, "name": node.name, "stage": node.stage, "skill": node.skill,
            "skillDir": skill_dir(skill_dirs, node.skill), "seq": node.seq, "order": node.order,
            "terminal": node.terminal, "checkpoints": list(node.checkpoints),
            "inputs": [{"id": ref.artifact, "required": ref.required} for ref in node.inputs],
            "outputs": [{"id": ref.artifact, "required": ref.required} for ref in node.outputs],
            "validate": node.validate,
        } for node in ir.nodes],
        "dynamicStages": [],
        "skip": None,
        "checkpoints": {"chain": list(ir.checkpoint_chain), "initial": ir.checkpoint_chain[0], "labels": labels},
    }


def framework_contribution(ir, normalized, skill_dirs: dict) -> Contribution:
    files = [FileSpec(path, "managed", src=path) for path in FRAMEWORK_FILES]
    files += [FileSpec(f".scaffold/{name}", "managed", src=f"schemas/{name}") for name in SCHEMA_FILES]
    files.append(FileSpec(GUARD_SCRIPT, "managed", src="runtime/hooks/artifact_guard.py"))
    files.append(FileSpec("plugin.json", "generated", content=fsio.dump_json(plugin_manifest(ir.plugin))))
    return Contribution(files=files, runtime_config={"runtime": runtime_config(ir),
                                                     "flow": flow_config(ir, normalized, skill_dirs)},
                        hooks={"PreToolUse": [ARTIFACT_GUARD]})


def render_command(spec, interpreter: str, platform: str) -> str:
    if spec.value is not None:
        return spec.value
    command = f'{interpreter} -X utf8 "${{pluginPath}}/{spec.script}"'
    args = spec.args.replace("{platform}", platform)
    return f"{command} {args}" if args else command


def render_board_core(board_options: dict, merged, modules: dict) -> dict:
    target = board_options.get("target", {})
    python = target.get("python", {})
    platforms = list(dict.fromkeys(target.get("platforms", ["darwin", "linux", "win32"])))
    commands = {}
    for platform in platforms:
        interpreter = python.get("win32", "python") if platform == "win32" else python.get("posix", "python3")
        commands[platform] = {key: render_command(spec, interpreter, platform)
                              for key, (_, spec) in merged.inspect_commands.items()}
    states = {}
    for module_id in MODULE_KEYS:
        if module_id in modules:
            states[module_id] = {"enabled": True, "version": modules[module_id].version,
                                 **merged.manifests.get(module_id, {})}
        else:
            states[module_id] = {"enabled": False}
    board_config = {"apiVersion": API_VERSION, "inspectCommands": commands}
    modules_json = {"apiVersion": API_VERSION, "modules": states, "boardEvents": dict(BOARD_EVENTS), **merged.entries}
    return {"board_core/board_config.json": fsio.dump_json(board_config),
            "board_core/modules.json": fsio.dump_json(modules_json)}
