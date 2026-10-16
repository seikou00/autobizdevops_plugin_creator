#!/usr/bin/env python3
"""演示版 simulate：在临时工作区按 DevClaw 的方式调用一遍生成的插件（interfaces.md §1.5）。

1. create_project、create_feature、dynamic_workflow、project_status；
2. 每个节点依次：session_context_inject → 推进 _in_progress → 写入桩产物 → 推进 _done（执行校验命令）→ feature_status；
3. 检查每次输出的结构，打印节点状态表和失败原因。

桩产物通常过不了业务校验，--skip-validate 跳过校验命令（在进程内调用 engine，命令行入口不提供这个开关）。
用法：python3 demo_simulate.py <插件目录> [--feature demo] [--to <checkpoint>] [--platform <p>] [--skip-validate] [--keep]
退出码：0 全部通过；1 有步骤失败；2 用法错误。
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = "demo-project"
SKIP_VALIDATE = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runtime.common import engine
from runtime.common.query import BoardError
try:
    result = engine.transition(Path(sys.argv[2]), sys.argv[3], sys.argv[4], _skip_validate=True)
except BoardError as error:
    result = {"ok": False, "errors": [str(error)]}
print(json.dumps(result, ensure_ascii=False))
sys.exit(0 if result.get("ok") else 1)
"""


class Simulation:
    def __init__(self, plugin, platform, feature, temp):
        self.plugin, self.platform, self.feature = plugin, platform, feature
        self.board = json.loads((plugin / "board_core" / "board_config.json").read_text(encoding="utf-8"))
        self.commands = self.board["inspectCommands"][platform]
        self.workspace = temp / "ws"
        self.project = self.workspace / PROJECT
        self.session = temp / "session"
        self.project.mkdir(parents=True)
        self.session.mkdir()
        self.values = {"pluginPath": str(plugin), "pluginWorkspace": str(self.workspace), "projectDir": PROJECT,
                       "feature": feature, "sessionWorkspacePath": str(self.session)}
        self.env = {**os.environ, "PLUGIN_WORKSPACE": str(self.workspace), "PROJECT_DIR": PROJECT,
                    "FEATURE_ID": feature, "SESSION_ID": "simulate", "PYTHONIOENCODING": "utf-8"}
        self.rows, self.failed = [], False
        self.python = None

    def interpreter(self, name):
        found = shutil.which(name)
        if found is None:
            self.note(f"本机找不到宿主命令中的解释器 {name}，改用 {sys.executable}")
        return found or sys.executable

    def host_args(self, key):
        """与宿主相同：先把命令拆成参数，再逐个替换占位符；多值占位符展开成多个参数。"""
        args = []
        for token in shlex.split(self.commands[key]):
            if token == "${projectDirs...}":
                args.append(PROJECT)
            elif token == "${selectedDeployUnits}":
                args.append("[]")
            else:
                for name, value in self.values.items():
                    token = token.replace("${" + name + "}", value)
                args.append(token)
        if self.python is None:
            self.python = self.interpreter(args[0])
        args[0] = self.python
        return args

    def run(self, args):
        completed = subprocess.run(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            payload = json.loads(completed.stdout.decode("utf-8"))
        except ValueError:
            payload = None
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        return completed.returncode, payload, stderr

    def record(self, step, ok, detail=""):
        self.rows.append((step, ok, detail))
        if not ok:
            self.failed = True
        return ok

    def note(self, text):
        self.rows.append(("注意", None, text))

    def host(self, key, check):
        code, payload, stderr = self.run(self.host_args(key))
        if payload is None:
            return self.record(key, False, f"stdout 不是 JSON（退出码 {code}）{stderr[-300:]}"), None
        problem = check(code, payload)
        return self.record(key, not problem, problem or describe(key, payload)), payload

    def update(self, checkpoint, skip_validate):
        if skip_validate:
            args = [self.python or sys.executable, "-c", SKIP_VALIDATE, str(self.plugin), str(self.project),
                    self.feature, checkpoint]
        else:
            args = [self.python or sys.executable, str(self.plugin / "runtime" / "workflow" / "update_state.py"),
                    "--feature", self.feature, "--checkpoint", checkpoint]
        code, payload, stderr = self.run(args)
        if payload is None:
            return self.record(f"→ {checkpoint}", False, f"stdout 不是 JSON（退出码 {code}）{stderr[-300:]}")
        if code != 0 or not payload.get("ok"):
            return self.record(f"→ {checkpoint}", False, "；".join(payload.get("errors", [])) or f"退出码 {code}")
        validation = payload.get("validation")
        if validation:
            detail = f"校验通过（{validation['durationMs']} ms）"
        elif payload.get("warnings"):
            detail = "；".join(payload["warnings"])
        else:
            detail = "无变化" if not payload.get("changed") else ""
        return self.record(f"→ {checkpoint}", True, detail)

    def write_stubs(self, node):
        directory = self.project / Path(*meta_dir(self.board, self.plugin).split("/")) / "features" / self.feature
        written = []
        for artifact in node["artifacts"]["outputs"]:
            for pattern in artifact.get("paths", [artifact["path"]]):
                relative = pattern.replace("**/", "").replace("*", "demo").replace("?", "x")
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text(f"# 模拟产物：{artifact['label']}\n\nsimulate 写入的桩内容。\n", encoding="utf-8")
                written.append(relative)
        self.record("写入桩产物", True, "、".join(written) or "本节点没有输出")


def meta_dir(board, plugin):
    runtime = json.loads((plugin / "runtime" / "config" / "runtime.json").read_text(encoding="utf-8"))
    return ".autobizdevops" if runtime["layout"] == "legacy" else f".autobizdevops/{runtime['pluginId']}"


def describe(key, payload):
    if key == "create_feature":
        return payload.get("checkpoint", "")
    if key == "dynamic_workflow":
        return f"{len(payload.get('nodes', []))} 个节点"
    if key == "session_context_inject":
        flow, agent = payload.get("flow", {}), payload.get("agentConfig", {})
        return f"目标节点 {flow.get('targetNodeId')}，agentMode {agent.get('agentMode')}"
    if key == "feature_status":
        return "、".join(f"{node['id']}:{node['nodeStatus']}" for node in payload["run"]["nodes"])
    return ""


def expect_ok(code, payload):
    if code != 0 or payload.get("ok") is False:
        return "；".join(payload.get("errors", [])) or payload.get("message", "") or f"退出码 {code}"
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(description="演示版 simulate：在临时工作区模拟 DevClaw 调用")
    parser.add_argument("plugin_dir", nargs="?", default=".")
    parser.add_argument("--feature", default="demo")
    parser.add_argument("--to", help="停在哪个 checkpoint")
    parser.add_argument("--platform", choices=["darwin", "linux", "win32"])
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--keep", action="store_true", help="保留临时目录")
    args = parser.parse_args(argv)
    plugin = Path(args.plugin_dir).expanduser().resolve()
    if not (plugin / "board_core" / "board_config.json").is_file():
        print(f"用法错误：{plugin} 还没有 build（找不到 board_core/board_config.json）", file=sys.stderr)
        return 2
    platform = args.platform or {"win32": "win32", "darwin": "darwin"}.get(sys.platform, "linux")
    temp = Path(tempfile.mkdtemp(prefix="autobiz-simulate-"))
    try:
        sim = Simulation(plugin, platform, args.feature, temp)
        nodes = sim.board["workflow"]["nodes"]
        chain = [checkpoint for node in nodes for checkpoint in node["checkpoints"]]
        if args.to and args.to not in chain:
            print(f"用法错误：--to {args.to} 不是本插件的 checkpoint：{'、'.join(chain)}", file=sys.stderr)
            return 2
        sim.host("create_project", expect_ok)
        sim.host("create_feature", lambda code, payload: expect_ok(code, payload) or (
            "" if payload.get("checkpoint") == chain[0] else f"初始 checkpoint 应为 {chain[0]}"))
        sim.host("dynamic_workflow", lambda code, payload: expect_ok(code, payload) or (
            "" if len(payload.get("nodes", [])) == len(nodes) else "节点数量与 board_config 不一致"))
        sim.host("project_status", lambda code, payload: expect_ok(code, payload) or (
            "" if any(run["featureId"] == args.feature for run in payload.get("projects", {}).get(PROJECT, {}).get("runs", []))
            else "project_status 中没有新建的 Feature"))
        for index, node in enumerate(nodes):
            if sim.failed:
                break
            sim.rows.append((f"── {node['id']} {node['label']}（/{node['skill']}）", None, ""))
            sim.host("session_context_inject", lambda code, payload, node=node: expect_ok(code, payload) or (
                "" if payload.get("flow", {}).get("targetNodeId") == node["id"]
                else f"策略目标节点应为 {node['id']}，实际为 {payload.get('flow', {}).get('targetNodeId')}"))
            start, finish = node["checkpoints"]
            if not sim.update(start, False) or args.to == start:
                break
            sim.write_stubs(node)
            if not sim.update(finish, args.skip_validate):
                break
            expected = ["done"] * (index + 1) + ["not_started"] * (len(nodes) - index - 1)
            sim.host("feature_status", lambda code, payload, expected=expected: expect_ok(code, payload) or (
                "" if [item["nodeStatus"] for item in payload["run"]["nodes"]] == expected
                else f"节点状态应为 {expected}"))
            if args.to == finish:
                break
        print(f"simulate：{plugin.name}（{platform}），临时工作区 {temp}")
        for step, ok, detail in sim.rows:
            mark = "  " if ok is None else ("✓ " if ok else "✗ ")
            print(f"  {mark}{step}" + (f"：{detail}" if detail else ""))
        if args.skip_validate:
            print("  已跳过校验命令（--skip-validate）")
        print("结果：" + ("有步骤失败，见上面的 ✗" if sim.failed else "全部通过"))
        return 1 if sim.failed else 0
    finally:
        if args.keep:
            print(f"已保留临时目录：{temp}")
        else:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
