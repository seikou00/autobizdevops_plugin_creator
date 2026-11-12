"""推导规则的唯一实现（input-config.md §2.3、§6）。lint 和 compile 都调用这里。"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLUGIN_PREFIX = "AutoBizDevOps_"


def prefixed_plugin_field(value: str) -> str:
    if not value or value.startswith(PLUGIN_PREFIX):
        return value
    return PLUGIN_PREFIX + value


GROUPS = ("biz", "dev", "ops")
# 节点技能所在的分组目录：skills/<分组目录>/<技能>/（D64）
SKILL_GROUP_DIRS = {"biz": "autobiz", "dev": "autodev", "ops": "autoops"}


def skill_target(group: str, skill: str) -> str:
    """节点技能应在的目录：按节点所属阶段放进 skills/autobiz|autodev|autoops/<技能>/。"""
    return f"skills/{SKILL_GROUP_DIRS[group]}/{skill}"

GLOB_CHARS = ("*", "?", "[")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED_PATHS = ("state.json", "hooks.ndjson", "sync-status.json", "ARTIFACT_CATALOG.json")


def group_label(group: str) -> str:
    return group[:1].upper() + group[1:]


def has_glob(path: str) -> bool:
    return any(char in path for char in GLOB_CHARS)


def artifact_id(path: str) -> str:
    """取最后一个不含 glob 的段 → 转小写、去掉结尾的 .md → 非 [a-z0-9] 连续字符换成 _，去掉首尾的 _。

    每一段都含 glob 时返回空字符串，由 lint 报 ARTIFACT_ID_INVALID。
    """
    segments = [segment for segment in path.split("/") if segment and not has_glob(segment)]
    if not segments:
        return ""
    name = segments[-1].lower()
    if name.endswith(".md"):
        name = name[:-3]
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def artifact_type(path: str) -> str:
    return "json" if path.lower().endswith(".json") else "file"


def output_item(item) -> tuple[str, bool]:
    """输出项 → (路径, required)。"""
    if isinstance(item, dict):
        return item["path"], not item.get("optional", False)
    return item, True


@dataclass(frozen=True)
class NodeRef:
    group: str
    index: int
    node: dict

    @property
    def pointer(self) -> str:
        return f"/nodes/{self.group}/{self.index}"


def grouped_nodes(workflow: dict) -> list[NodeRef]:
    nodes = workflow.get("nodes", {})
    return [NodeRef(group, index, node) for group in GROUPS for index, node in enumerate(nodes.get(group) or [])]


def ordered_nodes(workflow: dict) -> list[NodeRef]:
    """按 seq 升序；seq 重复时按分组和下标稳定排序（重复本身由 SEQ_DUP 报出）。"""
    refs = grouped_nodes(workflow)
    return sorted(refs, key=lambda ref: (ref.node.get("seq", 0), GROUPS.index(ref.group), ref.index))


def checkpoints(node_id: str, terminal: bool) -> tuple[str, ...]:
    return ("archived",) if terminal else (f"{node_id}_in_progress", f"{node_id}_done")


def unsafe_path(path: str) -> str:
    """产物路径不安全时返回原因，否则返回空字符串（PATH_UNSAFE）。"""
    if not path:
        return "路径为空"
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "不能是绝对路径"
    if "\\" in path:
        return "不能含 \\，路径分隔符用 /"
    if ":" in path:
        return "不能含 :"
    if ".." in path.split("/"):
        return "不能含 .. 段"
    if path.split("/")[0] in RESERVED_PATHS or path in RESERVED_PATHS:
        return "与保留文件名冲突（" + "、".join(RESERVED_PATHS) + "）"
    return ""
