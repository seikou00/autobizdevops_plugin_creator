#!/usr/bin/env python3
"""宿主钩子（PreToolUse：write_file、edit_file、apply_patch）：不允许直接改写状态文件。

<metaRoot>/state.json 归运行框架所有，只能通过技能开头状态维护片段里的 runtime/workflow/update_state.py 变更
（阶段回退由 rollback_stage.py 调用运行框架的重开）。直接写这个文件会绕过加锁、boardSeq 和看板事件。
取代原插件 hooks/state_checkpoint.py state-done。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.common import query  # noqa: E402

BLOCK_EXIT_CODE = 2
PATH_KEYS = ("filePath", "file_path", "path", "target_file")
PATCH_MARKERS = ("*** Update File:", "*** Add File:", "*** Delete File:", "+++ b/", "--- a/")


def candidate_paths(tool_input: dict) -> list[str]:
    paths = [tool_input[key] for key in PATH_KEYS if isinstance(tool_input.get(key), str)]
    for key in ("paths", "files"):
        values = tool_input.get(key)
        if isinstance(values, list):
            paths += [value for value in values if isinstance(value, str)]
    for key in ("patch", "input", "content"):
        text = tool_input.get(key)
        if isinstance(text, str) and "***" in text or isinstance(text, str) and "+++ " in text:
            for line in text.splitlines():
                for marker in PATCH_MARKERS:
                    if line.startswith(marker):
                        paths.append(line[len(marker):].strip())
    return paths


def is_state_file(value: str, cwd: Path) -> bool:
    path = Path(value.replace("\\", "/"))
    if not path.is_absolute():
        path = cwd / path
    parts = tuple(part for part in path.as_posix().split("/") if part and part != ".")
    suffix = tuple(part for part in query.meta_root().replace("\\", "/").split("/") if part) + ("state.json",)
    return parts[-len(suffix):] == suffix


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except (UnicodeDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cwd = Path(payload.get("cwd") or Path.cwd())
    try:
        targets = [value for value in candidate_paths(tool_input) if is_state_file(value, cwd)]
    except (query.BoardError, OSError, ValueError):
        return 0
    if not targets:
        return 0
    reason = ("状态文件不允许直接修改：" + "、".join(targets) + "。checkpoint 只能由技能开头状态维护片段中的 "
              "runtime/workflow/update_state.py 推进；阶段回退使用 autobizdevops-rollback 技能。")
    sys.stderr.write(reason + "\n")
    json.dump({"decision": "block", "reason": reason, "systemMessage": "不要直接编辑 state.json"}, sys.stdout,
              ensure_ascii=False)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
