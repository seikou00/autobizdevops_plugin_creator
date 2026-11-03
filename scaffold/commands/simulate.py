"""simulate 与 check 的契约测试：在临时目录中按宿主的方式调用一遍已生成的插件（interfaces.md §1.5，D55）。"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

from scaffold.build.manifest import read_manifest
from scaffold.commands import CommandResult
from scaffold.commands.package import collect
from scaffold.host import Host
from scaffold.lib import fsio, skillmd
from scaffold.lib.issues import Report, UsageError, error, warning
from scaffold.lib.tree import Tree
from scaffold.shapes import check_shape

PROJECT = "demo-project"
READ_ONLY = ("project_status", "feature_status", "dynamic_workflow", "session_collector_context_inject",
             "deploy_units")


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    return "darwin" if sys.platform == "darwin" else "linux"


def stub_path(pattern: str) -> str:
    return pattern.replace("**", "demo").replace("*", "demo").replace("?", "x")


def snapshot(directory: Path) -> dict:
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def state_commands(text: str) -> dict:
    """状态维护片段中的“技能开始执行”“技能完成执行”两条命令。"""
    inner = skillmd.state_inner(text) or ""
    commands = {}
    for line in inner.splitlines():
        for label, key in (("技能开始执行：", "start"), ("技能完成执行：", "finish")):
            if line.startswith(label):
                commands[key] = line[len(label):].strip()
    return commands


class Contract:
    def __init__(self, root: Path, *, platform: str | None, feature: str, to: str | None, keep: bool):
        self.root = Path(root)
        self.platform = platform or current_platform()
        self.feature = feature
        self.to = to
        self.keep = keep
        self.issues: list = []
        self.steps: list = []
        self.nodes: list = []
        self.stopped_at = None

    # —— 记录 ——

    def fail(self, step: dict, message: str, *, skill_file: str = "") -> None:
        step["ok"] = False
        step["detail"] = message
        if skill_file:
            self.issues.append(error("CONTRACT_TEST", f"{step['key']}：{message}", file=skill_file))
        else:
            self.issues.append(error("CONTRACT_TEST", f"{step['key']}：{message}", file="board_core/board_config.json",
                                     pointer=f"/inspectCommands/{self.platform}/{step['key']}"))

    def call(self, key: str, *, node=None, expect_ok: bool = True, read_only: bool = False, skill_file: str = "",
             command: str | None = None, session: dict | None = None):
        before = snapshot(self.workspace) if read_only else None
        if command is None:
            result = self.host.run(key, self.values)
        else:
            result = self.host.run_model(command, self.values, session or {})
        step = {"node": node, "key": result.key, "ok": True, "exitCode": result.code, "detail": ""}
        self.steps.append(step)
        payload = result.payload
        if result.error:
            self.fail(step, result.error + (f"；stderr: {result.stderr.strip()[-300:]}" if result.stderr.strip() else ""),
                      skill_file=skill_file)
            return None
        problems = check_shape(key, payload)
        if problems:
            pointer, reason = problems[0]
            self.fail(step, f"输出结构不符合 schemas/host/outputs.schema.json：{pointer or '/'} {reason}",
                      skill_file=skill_file)
            return payload
        if expect_ok and (payload.get("ok") is False or (result.code not in (0, None) and "ok" not in payload)):
            self.fail(step, "返回失败：" + "；".join(payload.get("errors", [])) or f"退出码 {result.code}",
                      skill_file=skill_file)
            return payload
        if read_only and snapshot(self.workspace) != before:
            self.fail(step, "只读命令修改了工作区中的文件", skill_file=skill_file)
        return payload

    # —— 流程 ——

    def prepare(self, base: Path) -> None:
        tree = Tree(self.root)
        entry = fsio.parse_json(tree.read_bytes("plugin.scaffold.json"))
        modules = entry.get("modules") or {}
        files, _ = collect(self.root, entry, read_manifest(tree), knowledge_enabled="knowledge" in modules,
                           knowledge_source=False)
        plugin = base / "plugin"
        for rel in files:
            target = plugin / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / rel, target)
        if (self.root / "sys").is_dir() and not (plugin / "sys").exists():
            shutil.copytree(self.root / "sys", plugin / "sys")
        self.plugin = plugin
        self.workspace = base / "ws"
        (self.workspace / PROJECT).mkdir(parents=True)
        (base / "session").mkdir()
        self.flow = fsio.parse_json((plugin / "runtime" / "config" / "flow.json").read_bytes())
        try:
            self.host = Host(plugin, self.workspace, self.platform)
        except KeyError:
            raise UsageError(f"board_config.json 中没有平台 {self.platform} 的命令") from None
        self.values = {"pluginPath": str(plugin), "pluginWorkspace": str(self.workspace), "projectDir": PROJECT,
                       "projectDirs...": [PROJECT], "feature": self.feature, "selectedDeployUnits": "[]",
                       "sessionWorkspacePath": str(base / "session"), "knowledge-path": ""}

    def run(self) -> dict:
        chain = None
        base = Path(tempfile.mkdtemp(prefix="autobiz-simulate-"))
        try:
            self.prepare(base)
            chain = self.flow["checkpoints"]["chain"]
            if self.to is not None and self.to not in chain:
                raise UsageError(f"--to {self.to} 不是 flow.json 中的 checkpoint：{'、'.join(chain)}")
            self.walk()
        finally:
            for message in getattr(self, "host", None).warnings if hasattr(self, "host") else []:
                self.issues.append(warning("INTERPRETER_MISSING", message, file="board_core/board_config.json",
                                           pointer=f"/inspectCommands/{self.platform}"))
            if not self.keep:
                shutil.rmtree(base, ignore_errors=True)
        return {"ran": True, "platform": self.platform, "feature": self.feature,
                "workspace": str(base) if self.keep else None, "stale": False, "stoppedAt": self.stopped_at,
                "steps": self.steps, "nodes": self.nodes}

    def walk(self) -> None:
        for attempt in (1, 2):
            payload = self.call("create_project")
            if payload is None or not self.steps[-1]["ok"]:
                return
            if payload.get("created") is not (attempt == 1):
                self.fail(self.steps[-1], f"第 {attempt} 次执行时 created 应为 {attempt == 1}")
        initial = self.flow["checkpoints"]["initial"]
        for attempt in (1, 2):
            payload = self.call("create_feature")
            if payload is None or not self.steps[-1]["ok"]:
                return
            self.steps[-1]["detail"] = payload.get("checkpoint", "")
            if payload.get("created") is not (attempt == 1) or payload.get("checkpoint") != initial:
                self.fail(self.steps[-1], f"第 {attempt} 次执行时应返回 created={attempt == 1}、checkpoint={initial}")
        feature_dir = Path(payload["featureDir"])
        self.call("dynamic_workflow", read_only=True)
        status = self.call("project_status", read_only=True)
        if not status or "workflow" not in status:
            return
        nodes = status["workflow"]["nodes"]
        if [node["id"] for node in nodes] != [node["id"] for node in self.flow["nodes"]]:
            self.fail(self.steps[-1], "workflow.nodes 与 flow.json 的节点不一致")
        if "deploy_units" in self.host.commands:
            before = len(self.issues)
            payload = self.call("deploy_units", expect_ok=False, read_only=True)
            if payload is not None and payload.get("ok") is False and len(self.issues) == before:
                self.issues.append(warning("KNOWLEDGE_MANIFEST_MISSING", "知识目录中没有清单，deploy_units 返回失败："
                                           + "；".join(payload.get("errors", [])),
                                           file="board_core/board_config.json",
                                           pointer=f"/inspectCommands/{self.platform}/deploy_units"))
        for index, node in enumerate(self.flow["nodes"]):
            if not self.advance(index, node, feature_dir):
                return

    def advance(self, index: int, node: dict, feature_dir: Path) -> bool:
        skill_file = f"{node['skillDir']}/SKILL.md"
        session = self.call("session_collector_context_inject", node=node["id"], read_only=True)
        if session is not None and session.get("flow", {}).get("targetNodeId") != node["id"]:
            self.fail(self.steps[-1], f"策略目标节点应为 {node['id']}，实际为 {session.get('flow', {}).get('targetNodeId')}")
        text = skillmd.read_text((self.plugin / skill_file).read_bytes())
        commands = state_commands(text)
        env = {"PLUGIN_WORKSPACE": str(self.workspace), "PROJECT_DIR": PROJECT, "FEATURE_ID": self.feature,
               "SESSION_ID": "simulate"}
        if not node.get("terminal"):
            if "start" not in commands:
                self.fail({"node": node["id"], "key": "model:update_state"}, "状态维护片段中没有开始命令",
                          skill_file=skill_file)
                return False
            payload = self.call("model:update_state", node=node["id"], skill_file=skill_file,
                                command=commands["start"], session=env)
            if payload is None or not self.steps[-1]["ok"]:
                return False
            self.steps[-1]["detail"] = payload.get("checkpoint", "")
            if self.stop_here(payload.get("checkpoint")):
                return False
            for ref in node.get("outputs", []):
                if not ref["required"]:
                    continue
                for pattern in self.flow["artifacts"][ref["id"]]["paths"]:
                    target = feature_dir / stub_path(pattern)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("simulate\n", encoding="utf-8")
        if "finish" not in commands:
            self.fail({"node": node["id"], "key": "model:update_state"}, "状态维护片段中没有完成命令", skill_file=skill_file)
            return False
        payload = self.call("model:update_state", node=node["id"], skill_file=skill_file, command=commands["finish"],
                            session=env)
        if payload is None or not self.steps[-1]["ok"]:
            return False
        self.steps[-1]["detail"] = payload.get("checkpoint", "")
        status = self.call("feature_status", node=node["id"], read_only=True)
        if status and "run" in status:
            self.nodes = [{"id": item["id"], "status": item["nodeStatus"]} for item in status["run"]["nodes"]]
            final = "archived" if node.get("terminal") else "done"
            expected = [final if i == index else "done" if i < index else "not_started"
                        for i in range(len(self.flow["nodes"]))]
            if [item["status"] for item in self.nodes] != expected:
                self.fail(self.steps[-1], f"节点状态应为 {expected}，实际为 {[item['status'] for item in self.nodes]}")
                return False
        return not self.stop_here(payload.get("checkpoint"))

    def stop_here(self, checkpoint) -> bool:
        if self.to is not None and checkpoint == self.to:
            self.stopped_at = checkpoint
            return True
        return False


def run_contract(root: Path, *, platform: str | None = None, feature: str = "demo", to: str | None = None,
                 keep: bool = False):
    """返回 (simulation, issues)。"""
    contract = Contract(root, platform=platform, feature=feature, to=to, keep=keep)
    simulation = contract.run()
    if any(not step["ok"] for step in contract.steps) and contract.stopped_at is None:
        checkpoints = [step["detail"] for step in contract.steps if step["key"] == "model:update_state" and step["ok"]]
        simulation["stoppedAt"] = checkpoints[-1] if checkpoints else None
    return simulation, contract.issues


def stale_inputs(tree: Tree, manifest: dict) -> list:
    """按 build-manifest 中 inputs 记录的键重算摘要，不执行 load、lint（Q11.4）。"""
    changed = []
    for key, recorded in manifest.get("inputs", {}).items():
        path, _, part = key.partition("#")
        data = tree.read_bytes(path)
        if data is None:
            changed.append(key)
            continue
        current = fsio.digest((skillmd.description_of(skillmd.read_text(data)) or "") if part == "description" else data)
        if current != recorded:
            changed.append(key)
    return changed


def simulate(root: Path, *, feature: str = "demo", to: str | None = None, platform: str | None = None,
             keep: bool = False) -> CommandResult:
    tree = Tree(root)
    manifest = read_manifest(tree)
    if manifest is None or not tree.is_file("board_core/board_config.json"):
        raise UsageError("插件还没有生成过，先执行 autobiz-plugin doctor")
    report = Report()
    changed = stale_inputs(tree, manifest)
    if changed:
        report.add("warning", "BUILD_STALE", "改了以下内容但没有重新生成，simulate 运行的是上次生成的插件：" + "、".join(changed),
                   file=changed[0].split("#", 1)[0], hint="执行 autobiz-plugin doctor")
    simulation, issues = run_contract(root, platform=platform, feature=feature, to=to, keep=keep)
    simulation["stale"] = bool(changed)
    report.extend(issues)
    table = "\n".join(f"{item['id']:<16} {item['status']}" for item in simulation["nodes"])
    failed = [step for step in simulation["steps"] if not step["ok"]]
    summary = "全部步骤通过" if not failed else f"{len(failed)} 个步骤失败"
    if simulation["workspace"]:
        summary += f"；临时目录保留在 {simulation['workspace']}"
    return CommandResult(report, extra={"simulation": simulation}, text=(table + "\n" if table else "") + summary)
