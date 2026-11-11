#!/usr/bin/env python3
"""宿主钩子（PreToolUse：execute）：节点完成前运行该节点的校验器，不通过就拦截完成命令。

命令是 runtime/workflow/update_state.py --checkpoint <节点>_done 时，按 skills/scripts/flowlib/node_contracts.json
中该节点的 validators 运行 stage_gate（与技能里手动执行的 stage_gate.py validate 相同）；有问题就返回 block。
声明了 refreshUiContextMd 的节点（specs）校验通过后重建 UI_CONTEXT.md。
节点没有声明校验器、重开、dry-run、已在该 checkpoint、无法定位项目或 Feature 时放行。
取代原插件 hooks/state_checkpoint.py autodev-lifecycle（原来在 update_checkpoint.py 推进时校验）。
命令解析沿用框架的 hooks/artifact_guard.py，两个钩子对同一条命令的判断一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "skills" / "scripts"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from hooks.artifact_guard import extract_command, invocations, parse, read_payload  # noqa: E402
from runtime.common import cli, query  # noqa: E402

BLOCK_EXIT_CODE = 2
MAX_ERRORS = 10


def problems_for(options: dict) -> tuple[str, list[str]]:
    checkpoint = options.get("checkpoint", "")
    if not checkpoint.endswith("_done") or options.get("reopen") or options.get("dry-run"):
        return checkpoint, []
    project = query.resolve_project(options.get("workspace"), options.get("project"))
    feature = query.resolve_feature(options.get("feature"))
    record = query.load_state(project)["features"].get(feature)
    if record is None or record.get("checkpoint") == checkpoint:
        return checkpoint, []
    from flowlib.contracts import load_contracts  # noqa: PLC0415
    from flowlib.stage_gate import validate_stage  # noqa: PLC0415

    from flowlib.contracts import EXTRAS_PATH, read_json  # noqa: PLC0415

    _, node, _ = query.locate(checkpoint)
    contract = load_contracts().contract_for_node(node["id"])
    extras = read_json(EXTRAS_PATH).get("nodes", {}).get(node["id"], {}) if EXTRAS_PATH.exists() else {}
    if contract.validators:
        result = validate_stage(workspace=project, feature=feature, stage=contract.node_id, phase="final")
        if not result.ok:
            return checkpoint, _problems(result)
    if extras.get("refreshUiContextMd"):
        # 原 update_checkpoint.py 在 specs_done 时重建 Plan 前的 UI_CONTEXT.md
        from flowlib.ui_context_writer import refresh_ui_context_md  # noqa: PLC0415

        try:
            refreshed = refresh_ui_context_md(project, feature, force_pre_plan=True)
        except Exception as error:  # noqa: BLE001
            return checkpoint, [f"ui_context_md_sync_failed：{error}"]
        if not refreshed:
            return checkpoint, ["ui_context_md_sync_failed：UI_CONTEXT.json 不存在或不可读取"]
    return checkpoint, []


def _problems(result) -> list[str]:
    problems = []
    for error in result.errors or [{"reason": "stage_gate_failed", "detail": ""}]:
        detail = error.get("detail") or error.get("message") or ""
        problems.append(f"{error.get('reason', 'invalid')}" + (f"：{detail}" if detail else ""))
    return problems


def main() -> int:
    cli.configure_stdio()
    blocked = []
    for args in invocations(extract_command(read_payload())):
        try:
            checkpoint, problems = problems_for(parse(args))
        except (query.BoardError, OSError, KeyError, ValueError):
            continue
        if problems:
            shown = problems[:MAX_ERRORS] + ([f"……另有 {len(problems) - MAX_ERRORS} 项"] if len(problems) > MAX_ERRORS else [])
            blocked.append(f"不能推进到 {checkpoint}，节点校验未通过：\n" + "\n".join(f"- {item}" for item in shown))
    if not blocked:
        return 0
    reason = "\n".join(blocked)
    sys.stderr.write(reason + "\n")
    json.dump({"decision": "block", "reason": reason,
               "systemMessage": "节点校验未通过：先按提示修正产物，再执行技能完成命令"}, sys.stdout, ensure_ascii=False)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
