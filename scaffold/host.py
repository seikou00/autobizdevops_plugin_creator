"""在脚手架中扮演 DevClaw：按宿主规则替换占位符、执行命令（scaffold.md 单元 11，D55）。"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scaffold.lib import fsio

SESSION_VARIABLES = ("PLUGIN_WORKSPACE", "PROJECT_DIR", "PROJECT_CODE", "FEATURE_ID", "SESSION_ID",
                     "AUTOBIZ_BOARD_ENDPOINT", "AUTOBIZ_BOARD_TOKEN")
PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")
TIMEOUT = 120


@dataclass
class HostCall:
    key: str
    argv: list
    code: int | None
    payload: dict | None
    stderr: str
    error: str = ""


class Host:
    def __init__(self, plugin_root: Path, workspace: Path, platform: str):
        self.plugin_root = Path(plugin_root)
        self.workspace = Path(workspace)
        self.platform = platform
        config = fsio.parse_json((self.plugin_root / "board_core" / "board_config.json").read_bytes())
        self.commands = config["inspectCommands"].get(platform)
        if self.commands is None:
            raise KeyError(platform)
        self.warnings: list = []

    def interpreter(self) -> str:
        """所选平台在 board.target.python 中配置的解释器：取该平台宿主命令开头的解释器（Q11.9）。"""
        for value in self.commands.values():
            if isinstance(value, str) and " -X utf8 " in value:
                return shlex.split(value)[0]
        return "python3"

    def resolve_interpreter(self, name: str) -> str:
        if shutil.which(name):
            return name
        message = f"PATH 上找不到解释器 {name}，已改用 {sys.executable}；DevClaw 在这台机器上执行同样会失败"
        if message not in self.warnings:
            self.warnings.append(message)
        return sys.executable

    @staticmethod
    def substitute(arg: str, values: dict) -> list:
        """先拆分、再逐个参数替换：${projectDirs...} 展开为多个参数，其余替换为文本（Q11.1）。"""
        whole = PLACEHOLDER.fullmatch(arg)
        if whole and isinstance(values.get(whole.group(1)), list):
            return [str(item) for item in values[whole.group(1)]]
        return [PLACEHOLDER.sub(lambda match: str(values.get(match.group(1), match.group(0))), arg)]

    def render(self, key: str, values: dict) -> list:
        argv = []
        for arg in shlex.split(self.commands[key]):
            argv.extend(self.substitute(arg, values))
        if argv:
            argv[0] = self.resolve_interpreter(argv[0])
        return argv

    def _env(self, extra: dict | None = None) -> dict:
        env = {key: value for key, value in os.environ.items() if key not in SESSION_VARIABLES}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(extra or {})
        return env

    def _run(self, key: str, argv: list, env: dict) -> HostCall:
        try:
            completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                       cwd=str(self.workspace), timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return HostCall(key, argv, None, None, "", f"超时（{TIMEOUT} 秒）")
        except OSError as error:
            return HostCall(key, argv, None, None, "", f"无法启动: {error}")
        stdout = completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr.decode("utf-8", "replace")
        try:
            payload = json.loads(stdout)
            if not isinstance(payload, dict):
                payload = None
        except ValueError:
            payload = None
        error = "" if payload is not None else f"stdout 不是一个 JSON 对象: {stdout[:200]!r}"
        return HostCall(key, argv, completed.returncode, payload, stderr, error)

    def run(self, key: str, values: dict) -> HostCall:
        """宿主命令只带参数，不注入会话变量（Q11.7）。"""
        return self._run(key, self.render(key, values), self._env())

    def run_model(self, command: str, values: dict, session: dict) -> HostCall:
        """执行技能状态维护片段中的命令：开头的 python 换成所选平台的解释器，注入会话变量。"""
        argv = []
        for arg in shlex.split(command):
            argv.extend(self.substitute(arg, values))
        if argv and argv[0] == "python":
            argv[0] = self.resolve_interpreter(self.interpreter())
        return self._run("model:update_state", argv, self._env(session))
