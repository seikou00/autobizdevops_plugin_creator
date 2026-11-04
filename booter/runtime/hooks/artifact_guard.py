"""宿主钩子：执行完成命令之前检查节点的必需产物存在且非空（interfaces.md §4.7）。

build 把它拷到插件根目录的 hooks/artifact_guard.py，在 hooks/hooks.json 中注册为 PreToolUse（execute）钩子。命令是
update_state.py --checkpoint <节点>_done 时，检查该节点的必需产物：缺失或为空就返回 block，阻止这次推进；
其他命令、重开、dry-run、已在该 checkpoint、无法定位项目或 Feature 时都放行（以 0 退出，不输出），
交给 update_state.py 自己报告。update_state.py 遇到缺失或为空的产物只报 warning，不阻止推进。
"""

import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.common import cli, engine, query  # noqa: E402

BLOCK_EXIT_CODE = 2
ENTRY = "update_state.py"
SHELL_FLAGS = ("-c", "-lc", "/c", "-Command")


def read_payload() -> dict:
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig") or "{}")
    except (UnicodeDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_command(payload: dict) -> str:
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    for value in (tool_input.get("command"), tool_input.get("cmd"), tool_input.get("script"), payload.get("command")):
        if isinstance(value, str) and value.strip():
            return value
    return ""


def split(command: str) -> list:
    try:
        return shlex.split(command.replace("\\", "/"))
    except ValueError:
        return command.replace("\\", "/").split()


def invocations(command: str) -> list:
    """命令中每一次 update_state.py 调用的参数；也展开 sh -c / cmd /c 这类包装，按 && ; | 拆开多条命令。"""
    found = []
    pending = [command]
    while pending:
        tokens = split(pending.pop())
        for index, token in enumerate(tokens):
            if token in SHELL_FLAGS and index + 1 < len(tokens):
                pending.append(tokens[index + 1])
        start = None
        for index, token in enumerate(tokens + ["&&"]):
            if token.strip("\"'").endswith(ENTRY):
                start = index + 1
            elif start is not None and token in ("&&", "||", ";", "|"):
                found.append(tokens[start:index])
                start = None
    return found


def parse(args: list) -> dict:
    options = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("--reopen", "--dry-run"):
            options[arg[2:]] = True
        elif arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            options[key] = value
        elif arg.startswith("--") and index + 1 < len(args):
            options[arg[2:]] = args[index + 1]
            index += 1
        index += 1
    return options


def problems_for(options: dict) -> tuple:
    """返回 (checkpoint, 问题列表)；不需要检查时问题列表为空。"""
    checkpoint = options.get("checkpoint", "")
    if not checkpoint.endswith("_done") or options.get("reopen") or options.get("dry-run"):
        return checkpoint, []
    project = query.resolve_project(options.get("workspace"), options.get("project"))
    feature = query.resolve_feature(options.get("feature"))
    record = query.load_state(project)["features"].get(feature)
    if record is None or record.get("checkpoint") == checkpoint:
        return checkpoint, []
    _, node, _ = query.locate(checkpoint)
    return checkpoint, engine.check_artifacts(project, feature, node.get("outputs", []))


def main() -> int:
    cli.configure_stdio()
    blocked = []
    for args in invocations(extract_command(read_payload())):
        try:
            checkpoint, problems = problems_for(parse(args))
        except (query.BoardError, OSError, KeyError, ValueError):
            continue
        blocked += [f"不能推进到 {checkpoint}：{problem}" for problem in problems]
    if not blocked:
        return 0
    reason = "\n".join(blocked)
    sys.stderr.write(reason + "\n")
    json.dump({"decision": "block", "reason": reason,
               "systemMessage": "必需产物缺失或为空：先补全产物，再执行技能完成命令"}, sys.stdout, ensure_ascii=False)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
