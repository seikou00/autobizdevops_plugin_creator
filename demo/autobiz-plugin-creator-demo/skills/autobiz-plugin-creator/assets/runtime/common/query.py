"""只读查询：读取编译配置和状态，定位项目、Feature、节点与产物（interfaces.md §4.6）。

只读：不执行校验命令、不修改状态、不运行技能；产物存在不代表节点已完成。
"""

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "runtime" / "config"
BOARD_CONFIG = ROOT / "board_core" / "board_config.json"
GLOB_TOKENS = ("*", "?", "[")


class BoardError(ValueError):
    """所有业务错误都抛这个类型，入口统一转成 {"ok": false, "errors": [...]}。"""


def plugin_root():
    return ROOT


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoardError(f"无法读取 {path}: {error}")


@lru_cache(maxsize=None)
def load_runtime():
    return read_json(CONFIG_DIR / "runtime.json")


def plugin_id():
    return load_runtime()["pluginId"]


@lru_cache(maxsize=None)
def load_session():
    return read_json(CONFIG_DIR / "session.json")


@lru_cache(maxsize=None)
def load_board():
    return read_json(BOARD_CONFIG)


@lru_cache(maxsize=None)
def load_flow():
    """读取 flow.json 并校验不变量（output-spec.md §5.2）。"""
    flow = read_json(CONFIG_DIR / "flow.json")
    nodes = flow["nodes"]
    chain = [checkpoint for node in nodes for checkpoint in node["checkpoints"]]
    if not nodes or len({node["id"] for node in nodes}) != len(nodes):
        raise BoardError("flow.json 节点为空或节点 id 重复")
    if len(chain) != len(set(chain)) or any(len(node["checkpoints"]) != 2 for node in nodes):
        raise BoardError("flow.json 的 checkpoint 重复，或节点不是恰好两个 checkpoint")
    if flow["checkpoints"]["chain"] != chain or flow["checkpoints"]["initial"] != chain[0]:
        raise BoardError("flow.json 的 checkpoint 链与节点顺序不一致")
    if set(flow["checkpoints"]["labels"]) != set(chain):
        raise BoardError("flow.json 的 labels 必须覆盖全部 checkpoint")
    for node in nodes:
        if not (ROOT / "skills" / node["skill"] / "SKILL.md").is_file():
            raise BoardError(f"技能不存在: skills/{node['skill']}/SKILL.md")
    for artifact in flow["artifacts"].values():
        for path in artifact["paths"]:
            safe_relative(path)
    return flow


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("/"):
        raise BoardError(f"必须是相对路径: {value!r}")
    if ".." in Path(value).parts:
        raise BoardError(f"路径不能越界: {value}")
    return value


def inside(base, path):
    resolved, base = Path(path).resolve(), Path(base).resolve()
    if resolved != base and base not in resolved.parents:
        raise BoardError(f"路径越出工作目录: {path}")
    return resolved


def safe_component(value, what):
    if not isinstance(value, str) or not value.strip() or value in (".", "..") \
            or any(token in value for token in ("/", "\\", "\0")):
        raise BoardError(f"{what}名称不合法: {value!r}")
    return value


def resolve_project(workspace=None, project=None):
    """显式参数优先；否则读 PLUGIN_WORKSPACE + PROJECT_DIR；拒绝插件安装目录。"""
    if workspace is None:
        workspace = os.environ.get("PLUGIN_WORKSPACE")
        project = project or os.environ.get("PROJECT_DIR") or os.environ.get("PROJECT_CODE")
        if not workspace or not project:
            raise BoardError("请传 --workspace 和 --project，或设置 PLUGIN_WORKSPACE 和 PROJECT_DIR")
    base = Path(workspace).expanduser().resolve()
    if project:
        base = inside(base, base / safe_component(project, "项目"))
    if not base.is_dir():
        raise BoardError(f"项目目录不存在: {base}")
    if base == ROOT or ROOT in base.parents:
        raise BoardError("业务状态不能写入插件安装目录")
    return base


def resolve_feature(feature=None, required=True):
    env_feature = os.environ.get("FEATURE_ID")
    if feature and env_feature and feature != env_feature:
        raise BoardError("--feature 与环境变量 FEATURE_ID 不一致")
    feature = feature or env_feature
    if not feature:
        if required:
            raise BoardError("请传 --feature，或设置 FEATURE_ID")
        return None
    return safe_component(feature, "Feature ")


def metadata_dir(project_path):
    """isolated：<project>/<metaRoot>/<pluginId>；legacy：<project>/<metaRoot>。metaRoot 默认 .autobizdevops。"""
    runtime = load_runtime()
    base = Path(project_path) / safe_relative(runtime["metaRoot"])
    inside(project_path, base)
    return base if runtime["layout"] == "legacy" else base / plugin_id()


def feature_dir(project_path, feature):
    return metadata_dir(project_path) / "features" / feature


def state_path(project_path):
    return metadata_dir(project_path) / "state.json"


def empty_state():
    return {"schemaVersion": 1, "pluginId": plugin_id(), "features": {}}


def load_state(project_path):
    path = state_path(project_path)
    if not path.exists():
        return empty_state()
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise BoardError("state.json 格式或 schemaVersion 不正确；原文件保留")
    if payload.get("pluginId") != plugin_id():
        raise BoardError("该目录属于其他插件的状态，不会读写；原文件保留")
    records = payload.get("features")
    if not isinstance(records, dict):
        raise BoardError("state.json.features 必须是对象")
    valid = set(load_flow()["checkpoints"]["chain"])
    for name, record in records.items():
        if not isinstance(record, dict) or record.get("checkpoint") not in valid or record.get("feature") != name:
            raise BoardError(f"Feature {name} 的状态记录无效；原文件保留")
    return payload


def list_features(project_path):
    return sorted(load_state(project_path)["features"])


def feature_record(project_path, feature):
    return load_state(project_path)["features"].get(feature)


def locate(checkpoint):
    """返回 (节点下标, 节点, "in_progress" | "done")。"""
    for index, node in enumerate(load_flow()["nodes"]):
        if checkpoint in node["checkpoints"]:
            return index, node, "done" if checkpoint == node["checkpoints"][1] else "in_progress"
    raise BoardError(f"未知 checkpoint: {checkpoint}")


def current_node(project_path, feature):
    record = feature_record(project_path, feature)
    if record is None:
        raise BoardError(f"Feature 不存在: {feature}")
    _, node, status = locate(record["checkpoint"])
    return node, status


def node_by_id(node_id):
    return next((node for node in load_flow()["nodes"] if node["id"] == node_id), None)


def node_by_skill(skill):
    return next((node for node in load_flow()["nodes"] if node["skill"] == skill), None)


def next_node(node_id):
    nodes = load_flow()["nodes"]
    for index, node in enumerate(nodes):
        if node["id"] == node_id:
            return nodes[index + 1] if index + 1 < len(nodes) else None
    return None


def node_skill(node_id):
    return node_by_id(node_id)["skill"]


def node_artifacts(node_id, direction="outputs"):
    artifacts = load_flow()["artifacts"]
    return [{"id": item, **artifacts[item]} for item in node_by_id(node_id)[direction]]


def checkpoint_chain():
    return list(load_flow()["checkpoints"]["chain"])


def stage_label(checkpoint):
    return load_flow()["checkpoints"]["labels"][checkpoint]


def _matches(directory, pattern):
    if any(token in pattern for token in GLOB_TOKENS):
        found = sorted(directory.glob(pattern))
    else:
        current = directory
        for component in Path(pattern).parts:
            if not current.is_dir():
                return []
            # 大小写不敏感的文件系统上也按实际拼写匹配
            current = next((entry for entry in current.iterdir() if entry.name == component), None)
            if current is None:
                return []
        found = [current]
    matched = []
    for path in found:
        if path.is_file():
            try:
                inside(directory, path)
            except BoardError:
                continue  # 拒绝指向产物目录之外的符号链接
            matched.append(path)
    return matched


def artifact_presence(project_path, feature, artifact_id):
    """每一项至少匹配一个普通文件即为存在；空文件也算存在（D13）。"""
    directory = feature_dir(project_path, feature)
    files, missing = [], []
    for pattern in load_flow()["artifacts"][artifact_id]["paths"]:
        matched = _matches(directory, pattern) if directory.is_dir() else []
        files.extend(matched)
        if not matched:
            missing.append(pattern)
    return {"exists": not missing, "files": files, "missing": missing}
