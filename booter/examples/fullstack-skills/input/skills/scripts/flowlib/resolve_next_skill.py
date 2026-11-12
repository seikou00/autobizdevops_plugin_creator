#!/usr/bin/env python3
"""Resolve the next workflow skill from the plugin-provided session context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "skills" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "skills" / "scripts"))

from flowlib.state_store import get_state_json_path, load_state_json_records_result  # noqa: E402
from runtime.common import query  # noqa: E402
from flowlib.paths import (  # noqa: E402
    contains_workspace_argument,
    get_plugin_output_workspace,
    resolve_env_feature,
)


CONTEXT_ARGUMENT_ERROR = (
    "resolve_next_skill.py 不接受 --workspace/-w 或 --feature/-f；"
    "路径和 Feature 由 PLUGIN_WORKSPACE/PROJECT_DIR/FEATURE_ID 环境变量决定。"
)


def _contains_feature_argument(args: list[str]) -> bool:
    return any(
        arg in {"--feature", "-f"}
        or arg.startswith("--feature=")
        or (arg.startswith("-f") and arg != "-f")
        for arg in args
    )


def _next_action(node_id: str, status: str) -> dict:
    """runtime/config/board.json 中节点在该状态下的 nextAction（看板上展示的下一步）。"""
    for group in query.load_board().get("nodes", {}).values():
        for node in group:
            if node.get("id") == node_id:
                action = (node.get("nextAction") or {}).get(status)
                return dict(action) if isinstance(action, dict) else {}
    return {}


def resolve_route(workspace: Path, feature: str) -> tuple[dict, int]:
    """当前 Feature 的下一步：当前节点、允许的下一 checkpoint、推荐技能。

    v1 运行框架只有 standard 流程，没有 profile、动态阶段和跳过节点，下一步完全由 flow.json 的 checkpoint 链决定。"""
    result = load_state_json_records_result(workspace)
    errors = list(result.fatal_errors)
    if not result.exists:
        errors.append(f"state.json 未找到: {get_state_json_path(workspace)}")
    record = result.records.get(feature)
    if record is None and not errors:
        errors.append(f"feature '{feature}' 未在 state.json 中找到")
    if errors or record is None:
        return {"ok": False, "feature": feature, "errors": errors}, 1
    checkpoint = record.get("checkpoint", "")
    if query.is_stranded(record):
        return {"ok": False, "feature": feature, "checkpoint": checkpoint, "errors": [query.stranded_reason(record)]}, 1
    _, node, status = query.locate(checkpoint)
    action = _next_action(node["id"], status)
    recommended = action.get("slashSkill", "")
    if not recommended and status != "archived":
        following = query.next_node(node["id"], record) if status == "done" else node
        recommended = following["skill"] if following else ""
    return {
        "ok": True,
        "feature": feature,
        "workflowProfile": record.get("workflowProfile", "standard"),
        "workflowTemplate": record.get("workflowTemplate", "standard"),
        "checkpoint": checkpoint,
        "currentNodeId": node["id"],
        "currentNodeStatus": status,
        "currentStateId": status,
        "allowedNextCheckpoints": query.allowed_next(checkpoint),
        "recommendedNextSkill": recommended,
        "requiresProfileChoice": False,
        "profileChoices": [],
        "requiresWorkflowChoice": False,
        "workflowChoices": [],
        "nextAction": action,
    }, 0


def _print_text(payload: dict) -> None:
    if not payload.get("ok"):
        print("NEXT_SKILL_FAIL")
        for error in payload.get("errors", []):
            print(f"- {error}")
        return

    print(f"feature: {payload.get('feature', '')}")
    print(f"checkpoint: {payload.get('checkpoint', '')}")
    print(f"workflowProfile: {payload.get('workflowProfile', '')}")
    recommended = payload.get("recommendedNextSkill") or payload.get("nextAction", {}).get("slashSkill", "")
    print(f"recommendedNextSkill: {recommended or 'none'}")
    allowed = payload.get("allowedNextCheckpoints", [])
    print("allowedNextCheckpoints: " + (", ".join(allowed) if allowed else "none"))
    if payload.get("requiresProfileChoice"):
        print("requiresProfileChoice: true")
        for choice in payload.get("profileChoices", []):
            print(
                "- "
                + f"{choice.get('id')}: {choice.get('label')} "
                + f"-> {choice.get('recommendedNextSkill') or 'none'}"
            )
    if payload.get("requiresWorkflowChoice"):
        print("requiresWorkflowChoice: true")
        for choice in payload.get("workflowChoices", []):
            print(
                "- "
                + f"{choice.get('stageId')}={choice.get('decision')}: {choice.get('label')} "
                + f"-> {choice.get('recommendedNextSkill') or 'none'}"
            )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if contains_workspace_argument(raw_args) or _contains_feature_argument(raw_args):
        print(CONTEXT_ARGUMENT_ERROR, file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(
        description="Resolve next workflow skill for the current Feature",
        allow_abbrev=False,
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(raw_args)

    try:
        workspace = get_plugin_output_workspace()
        feature = resolve_env_feature(None, required=True)
    except ValueError as exc:
        payload = {"ok": False, "errors": [f"下一技能解析失败: {exc}"]}
        if args.json:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            _print_text(payload)
        return 1

    payload, exit_code = resolve_route(workspace, feature)
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        _print_text(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
