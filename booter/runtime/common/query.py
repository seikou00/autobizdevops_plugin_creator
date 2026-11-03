"""只读查询：编译配置、状态、节点与产物存在情况（interfaces.md §4.6）。

只读 runtime/config/ 和项目目录下的 state.json，不执行校验命令、不修改状态。
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PLUGIN_ROOT / "runtime" / "config"
GLOB_CHARS = ("*", "?", "[")
STATE_SCHEMA_VERSION = 1
LEGACY_STATE_V3 = "autobizdevops.state.v3"
MIGRATED_FROM = "_migratedFrom"     # 只在内存中，写入前由 engine 去掉
UNSAFE_COMPONENT = re.compile(r"[/\\\x00]")


class BoardError(ValueError):
    """所有业务错误都抛这个类型；入口把它转成 {"ok": false, "errors": [...]}。"""


# —— 编译配置 ——

def plugin_root() -> Path:
    return PLUGIN_ROOT


@lru_cache(maxsize=None)
def load_config(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BoardError(f"缺少编译配置 runtime/config/{name}.json，请在插件目录执行 autobiz-plugin doctor") from None
    except (OSError, ValueError) as error:
        raise BoardError(f"无法读取 runtime/config/{name}.json: {error}") from None
    if not isinstance(value, dict):
        raise BoardError(f"runtime/config/{name}.json 必须是对象")
    return value


def runtime_config() -> dict:
    return load_config("runtime")


def plugin_id() -> str:
    return runtime_config()["pluginId"]


def meta_root() -> str:
    return runtime_config().get("metaRoot", ".autobizdevops")


def has_config(name: str) -> bool:
    return (CONFIG_DIR / f"{name}.json").is_file()


@lru_cache(maxsize=None)
def load_flow() -> dict:
    flow = load_config("flow")
    _check_flow(flow)
    return flow


def load_board() -> dict:
    return load_config("board")


def load_session() -> dict:
    return load_config("session") if has_config("session") else {"policies": {"default": {}, "nodes": {}},
                                                                 "knowledgeAssembly": None}


def _check_flow(flow: dict) -> None:
    """运行框架加载时校验的不变量（output-spec.md §5.2，D59）。"""
    if flow.get("dynamicStages"):
        raise BoardError("flow.json 中有动态阶段：v1 运行框架不支持（D59）")
    if flow.get("skip") is not None:
        raise BoardError("flow.json 的 skip 不为 null：v1 运行框架不支持跳过节点（D59）")
    nodes = flow.get("nodes") or []
    if not nodes:
        raise BoardError("flow.json 没有节点")
    ids = [node["id"] for node in nodes]
    if len(set(ids)) != len(ids):
        raise BoardError("flow.json 的节点 id 重复")
    seqs = [node["seq"] for node in nodes]
    if any(later <= earlier for earlier, later in zip(seqs, seqs[1:])):
        raise BoardError("flow.json 的节点 seq 必须严格递增")
    checkpoints = []
    for index, node in enumerate(nodes):
        expected = ["archived"] if node.get("terminal") else [f"{node['id']}_in_progress", f"{node['id']}_done"]
        if node.get("checkpoints") != expected:
            raise BoardError(f"节点 {node['id']} 的 checkpoint 应为 {expected}")
        if node.get("terminal") and index != len(nodes) - 1:
            raise BoardError(f"终态节点 {node['id']} 必须是最后一个节点")
        checkpoints.extend(expected)
        skill_md = PLUGIN_ROOT / node["skillDir"] / "SKILL.md"
        if not skill_md.is_file():
            raise BoardError(f"技能不存在: {node['skillDir']}/SKILL.md")
    contract = flow.get("checkpoints", {})
    if contract.get("chain") != checkpoints:
        raise BoardError("flow.json 的 checkpoint 链与节点顺序不一致")
    if contract.get("initial") != checkpoints[0]:
        raise BoardError("flow.json 的 initial 必须是首个节点的开始 checkpoint")
    if set(contract.get("labels", {})) != set(checkpoints):
        raise BoardError("flow.json 的 labels 必须覆盖全部 checkpoint")
    for artifact in flow.get("artifacts", {}).values():
        for pattern in artifact.get("paths", []):
            safe_relative(pattern)


def checkpoint_chain() -> list:
    return list(load_flow()["checkpoints"]["chain"])


def checkpoint_label(checkpoint: str) -> str:
    return load_flow()["checkpoints"]["labels"][checkpoint]


def nodes() -> list:
    return list(load_flow()["nodes"])


def node(node_id: str) -> dict:
    for item in nodes():
        if item["id"] == node_id:
            return item
    raise BoardError(f"未知节点: {node_id}")


def node_skill(node_id: str) -> str:
    return node(node_id)["skill"]


def node_by_skill(skill: str):
    return next((item for item in nodes() if item["skill"] == skill), None)


def node_artifacts(node_id: str, direction: str = "outputs") -> list:
    """节点的输入或输出：[{id, required, label, type, paths}]。"""
    artifacts = load_flow()["artifacts"]
    return [{**ref, **{key: artifacts[ref["id"]][key] for key in ("label", "type", "paths")}}
            for ref in node(node_id).get(direction, [])]


def locate(checkpoint: str):
    """checkpoint → (节点下标, 节点, "in_progress" | "done" | "archived")。"""
    for index, item in enumerate(nodes()):
        if checkpoint in item["checkpoints"]:
            if item.get("terminal"):
                return index, item, "archived"
            return index, item, "done" if checkpoint == item["checkpoints"][1] else "in_progress"
    raise BoardError(f"未知 checkpoint: {checkpoint}")


def current_node(record: dict):
    _, item, status = locate(record["checkpoint"])
    return item, status


def next_node(node_id: str, record: dict | None = None):
    """v1 按 seq 线性求下一节点；v2 再按 Feature 记录中的 workflowDecisions、workflowSkippedNodes 求。"""
    ids = [item["id"] for item in nodes()]
    index = ids.index(node_id)
    return nodes()[index + 1] if index + 1 < len(ids) else None


def active_nodes(record: dict | None = None) -> list:
    """该 Feature 实际经过的节点；v1 没有动态阶段和跳过，即全部节点。"""
    return nodes()


def allowed_next(checkpoint: str) -> list:
    chain = checkpoint_chain()
    index = chain.index(checkpoint)
    return chain[index + 1:index + 2]


# —— 定位 ——

def safe_relative(value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise BoardError(f"必须是相对路径: {value!r}")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise BoardError(f"路径不能越界: {value}")
    return path


def inside(base: Path, path: Path) -> Path:
    resolved = Path(path).resolve()
    base = Path(base).resolve()
    if resolved != base and base not in resolved.parents:
        raise BoardError(f"路径越出工作目录: {path}")
    return resolved


def safe_component(value, what: str) -> str:
    if not isinstance(value, str) or not value or value in (".", "..") or UNSAFE_COMPONENT.search(value):
        raise BoardError(f"{what}名称不合法: {value!r}（不能为空、不能是 . 或 ..，不能含 / \\）")
    return value


def resolve_project(workspace: str | None = None, project: str | None = None) -> Path:
    """显式参数优先；否则读 PLUGIN_WORKSPACE + PROJECT_DIR；拒绝插件安装目录。"""
    env_workspace = os.environ.get("PLUGIN_WORKSPACE")
    env_project = os.environ.get("PROJECT_DIR") or os.environ.get("PROJECT_CODE")
    if workspace is None:
        workspace = env_workspace
    project = project or env_project
    if not workspace or not project:
        raise BoardError("请传 --workspace 和 --project，或设置 PLUGIN_WORKSPACE 和 PROJECT_DIR")
    base = Path(workspace).expanduser().resolve()
    safe_component(project, "项目")
    path = inside(base, base / project)
    if not path.is_dir():
        raise BoardError(f"项目目录不存在: {path}")
    if path == PLUGIN_ROOT or PLUGIN_ROOT in path.parents:
        raise BoardError("业务状态不能写入插件安装目录")
    return path


def resolve_feature(feature: str | None = None, *, required: bool = True) -> str | None:
    env_feature = os.environ.get("FEATURE_ID")
    if feature and env_feature and feature != env_feature:
        raise BoardError(f"--feature {feature} 与环境变量 FEATURE_ID={env_feature} 不一致")
    feature = feature or env_feature
    if not feature:
        if required:
            raise BoardError("请传 --feature，或设置 FEATURE_ID")
        return None
    return safe_component(feature, "Feature ")


def metadata_dir(project_path: Path) -> Path:
    return inside(project_path, Path(project_path) / safe_relative(meta_root()))


def feature_dir(project_path: Path, feature: str) -> Path:
    base = metadata_dir(project_path)
    return inside(base, base / "features" / safe_component(feature, "Feature "))


def state_path(project_path: Path) -> Path:
    return metadata_dir(project_path) / "state.json"


def lock_path(project_path: Path) -> Path:
    return metadata_dir(project_path) / ".state.lock"


def hook_log_path(project_path: Path) -> Path:
    return metadata_dir(project_path) / "hooks.ndjson"


def relative_to_project(project_path: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(project_path).resolve()).as_posix()


# —— 状态 ——

def empty_state() -> dict:
    return {"schemaVersion": STATE_SCHEMA_VERSION, "pluginId": plugin_id(), "boardSeq": 0, "features": {}}


def _from_v3(payload: dict) -> dict:
    """全栈版的 autobizdevops.state.v3（不带 pluginId）当作本插件的旧格式读取（D60）。

    记录可以是对象或 checkpoint 字符串；已下架的 lean、custom 模板按 standard 继续，原值记在 legacyWorkflowTemplate。
    首次写入时由 engine 备份原文件并升级为 schemaVersion 1。
    """
    records = payload.get("features")
    if not isinstance(records, dict):
        raise BoardError("state.json（v3）的 features 必须是对象；原文件保留")
    features = {}
    for name, record in records.items():
        if isinstance(record, str):
            record = {"feature": name, "checkpoint": record}
        if not isinstance(record, dict):
            raise BoardError(f"Feature {name} 的状态记录无效；原文件保留")
        record = dict(record)
        record.setdefault("feature", name)
        for key in ("workflowTemplate", "workflowProfile"):
            if record.get(key, "standard") != "standard":
                record.setdefault(f"legacy{key[0].upper()}{key[1:]}", record[key])
                record[key] = "standard"
        features[name] = record
    return {"schemaVersion": STATE_SCHEMA_VERSION, "pluginId": plugin_id(), "boardSeq": 0, "features": features,
            MIGRATED_FROM: LEGACY_STATE_V3}


def load_state(project_path: Path) -> dict:
    """读取并校验 state.json。checkpoint 不在当前流程中的 Feature 原样保留、只读（is_stranded），不影响其他 Feature。"""
    path = state_path(project_path)
    if not path.exists():
        return empty_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise BoardError(f"state.json 无法解析，原文件保留: {error}") from None
    if isinstance(payload, dict) and payload.get("schemaVersion") == LEGACY_STATE_V3 and "pluginId" not in payload:
        payload = _from_v3(payload)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != STATE_SCHEMA_VERSION:
        raise BoardError("state.json 格式或 schemaVersion 不正确；原文件保留")
    if payload.get("pluginId") != plugin_id():
        raise BoardError(f"该目录的 state.json 属于插件 {payload.get('pluginId')!r}，不是 {plugin_id()}，不会读写；"
                         "同一项目安装多个插件时各插件要配置不同的 runtime.metaRoot")
    records = payload.get("features")
    if not isinstance(records, dict):
        raise BoardError("state.json 的 features 必须是对象")
    for name, record in records.items():
        if not isinstance(record, dict) or record.get("feature") != name or not isinstance(record.get("checkpoint"), str):
            raise BoardError(f"Feature {name} 的状态记录无效；原文件保留")
    seq = payload.get("boardSeq", 0)
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise BoardError("state.json 的 boardSeq 必须是非负整数")
    return payload


def is_stranded(record: dict) -> bool:
    """Feature 停在当前流程没有的 checkpoint 上（节点删除或改名、v3 的 needs_fix 等）：只能查看，不能推进。"""
    return record.get("checkpoint") not in checkpoint_chain()


def stranded_reason(record: dict) -> str:
    return (f"Feature {record.get('feature')} 停在 checkpoint {record.get('checkpoint')!r}，当前流程中没有这个 checkpoint，"
            "只能查看、不能推进；需要人工处理（例如手动改回某个节点的 checkpoint）")


def list_features(project_path: Path) -> list:
    payload = load_state(project_path)
    return [payload["features"][name] for name in sorted(payload["features"])]


def feature_record(project_path: Path, feature: str):
    return load_state(project_path)["features"].get(feature)


# —— 产物存在情况 ——

def _exact(directory: Path, path: Path) -> list:
    """不含 glob 的路径逐段按实际拼写匹配，大小写不敏感的文件系统上也区分大小写。"""
    current = directory
    for component in path.parts:
        if not current.is_dir():
            return []
        current = next((entry for entry in current.iterdir() if entry.name == component), None)
        if current is None:
            return []
    return [current]


def match_files(directory: Path, pattern: str) -> list:
    path = safe_relative(pattern)
    if not directory.is_dir():
        return []
    if any(char in pattern for char in GLOB_CHARS):
        matches = sorted(directory.glob(pattern))
    else:
        matches = _exact(directory, path)
    result = []
    for match in matches:
        if match.is_file():
            try:
                result.append(inside(directory, match))
            except BoardError:
                continue
    return result


def is_empty(path: Path) -> bool:
    try:
        return not path.read_bytes().strip()
    except OSError:
        return True


def artifact_presence(project_path: Path, feature: str, artifact_id: str) -> dict:
    """{"exists", "files", "missing", "empty"}；空文件不算存在；拒绝越界符号链接。"""
    artifact = load_flow()["artifacts"][artifact_id]
    directory = feature_dir(project_path, feature)
    files, missing, empty = [], [], []
    for pattern in artifact["paths"]:
        matched = match_files(directory, pattern)
        if not matched:
            missing.append(pattern)
        for path in matched:
            (empty if is_empty(path) else files).append(path)
    return {"exists": not missing and not empty, "files": files, "missing": missing, "empty": empty}
