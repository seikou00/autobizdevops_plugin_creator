"""节点契约：流程脚本按技能或节点查询输入、输出、checkpoint 和校验器（取代原插件的 board_core.contracts）。

数据来源：
- 运行框架编译出的 runtime/config/flow.json（经 runtime.common.query 读取）：节点、技能、checkpoint 链、输出产物。
  这是唯一的流程事实源，与状态维护片段、产物检查钩子 hooks/artifact_guard.py 一致；
- 同目录的 node_contracts.json：运行框架不管、流程脚本要用的扩展——输入产物（含缺失时的处理说明）、
  校验器清单、守卫、回退时归档的目录。

v1 运行框架只有 standard 一种流程：没有工作流 profile、模板、动态阶段和跳过节点，也没有 needs_fix。
原接口中与这些有关的参数照常接受、不再起作用，以免逐个改动调用方。

节点 id 沿用原插件带阶段前缀的写法（biz.prd、dev.plan），技能正文和校验器都按这个写法引用；
运行框架里的节点 id（prd、plan）放在 SkillContract.runtime_id，contract_for_node 两种写法都接受。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from runtime.common import query  # noqa: E402

EXTRAS_PATH = Path(__file__).with_name("node_contracts.json")
BASE_WORKFLOW_PROFILE = "standard"
BASE_WORKFLOW_TEMPLATE = "standard"
STAGE_PREFIX = {"Biz": "biz", "Dev": "dev", "Ops": "ops"}


class BoardConfigError(Exception):
    """流程契约无法使用：flow.json 缺失或无法解析、技能不绑定节点等。"""


WorkflowCompileError = BoardConfigError


@dataclass(frozen=True)
class ExtractSpec:
    """输入产物缺失时的处理说明。"""

    degrade: str = ""


@dataclass(frozen=True)
class ArtifactSpec:
    id: str
    label: str
    path: str
    kind: str = "file"
    required: bool = True
    extract: ExtractSpec | None = None


@dataclass(frozen=True)
class SkillContract:
    node_id: str
    label: str
    group: str
    skill: str
    checkpoints: tuple[str, ...]
    inputs: tuple[ArtifactSpec, ...]
    outputs: tuple[ArtifactSpec, ...]
    validators: tuple[str, ...]
    guards: tuple[str, ...] = ()
    runtime_id: str = ""

    @property
    def required_inputs(self) -> tuple[str, ...]:
        return tuple(artifact.path for artifact in self.inputs if artifact.required)

    @property
    def required_outputs(self) -> tuple[str, ...]:
        return tuple(artifact.path for artifact in self.outputs if artifact.required)


@dataclass(frozen=True)
class WorkflowContracts:
    nodes: tuple[dict, ...]
    profile: str
    skill_contracts: dict[str, SkillContract]
    known_checkpoints: frozenset[str]
    initial_checkpoints: frozenset[str]
    allowed_next: dict[str, frozenset[str]]
    stage_labels: dict[str, str]
    start_checkpoint_to_skill: dict[str, str]
    end_checkpoint_to_skill: dict[str, str]
    skipped_skills: dict[str, str] = field(default_factory=dict)

    def contract_for_skill(self, skill: str) -> SkillContract:
        try:
            return self.skill_contracts[skill]
        except KeyError:
            raise BoardConfigError(f"技能 {skill} 不绑定当前流程中的任何节点（workflow.json）") from None

    def contract_for_node(self, node_id: str) -> SkillContract:
        for contract in self.skill_contracts.values():
            if node_id in (contract.node_id, contract.runtime_id):
                return contract
        raise BoardConfigError(f"未知节点: {node_id}")


def qualified_id(node: dict) -> str:
    """flow.json 的节点 → 带阶段前缀的 id（dev.plan）。"""
    return f"{STAGE_PREFIX.get(node.get('stage'), str(node.get('stage', '')).lower())}.{node['id']}"


def runtime_node_id(node_id: str) -> str:
    """dev.plan 或 plan → plan。"""
    return node_id.split(".", 1)[1] if "." in node_id else node_id


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise BoardConfigError(f"{path} 无法读取: {error}") from None
    if not isinstance(value, dict):
        raise BoardConfigError(f"{path} 顶层必须是对象")
    return value


def _extract(value: Any) -> ExtractSpec | None:
    if isinstance(value, dict) and isinstance(value.get("degrade"), str):
        return ExtractSpec(value["degrade"])
    return None


def _input_specs(items: list) -> tuple[ArtifactSpec, ...]:
    return tuple(ArtifactSpec(id=item["id"], label=item.get("label", item["id"]), path=item["path"],
                              kind=item.get("kind", "file"), required=bool(item.get("required", True)),
                              extract=_extract(item.get("extract")))
                 for item in items or [])


def _output_specs(flow: dict, node: dict, labels: dict) -> tuple[ArtifactSpec, ...]:
    specs = []
    for ref in node.get("outputs", []):
        artifact = flow["artifacts"][ref["id"]]
        for path in artifact["paths"]:
            specs.append(ArtifactSpec(id=ref["id"], label=labels.get(path, artifact.get("label", path)), path=path,
                                      kind=artifact.get("type", "file"), required=bool(ref.get("required", True))))
    return tuple(specs)


def _legacy_node(contract: SkillContract, extras: dict, order: int) -> dict:
    """原 board_config 节点的写法，供按节点字典读取的调用方（rollback_stage 等）使用。"""
    def as_dict(spec: ArtifactSpec) -> dict:
        value = {"id": spec.id, "label": spec.label, "artifactType": spec.kind, "path": spec.path,
                 "required": spec.required}
        if spec.extract is not None:
            value["extract"] = {"degrade": spec.extract.degrade}
        return value
    return {"id": contract.node_id, "runtimeId": contract.runtime_id, "label": contract.label,
            "group": contract.group, "skill": contract.skill, "order": order, "checkpoints": list(contract.checkpoints),
            "artifacts": {"inputs": [as_dict(spec) for spec in contract.inputs],
                          "outputs": [as_dict(spec) for spec in contract.outputs]},
            "validators": list(contract.validators), "guards": list(contract.guards),
            "rollback": extras.get("rollback") or {}}


@lru_cache(maxsize=None)
def load_contracts() -> WorkflowContracts:
    try:
        flow = query.load_flow()
    except (OSError, ValueError) as error:
        raise BoardConfigError(f"runtime/config/flow.json 无法读取: {error}") from None
    extras = read_json(EXTRAS_PATH).get("nodes", {}) if EXTRAS_PATH.exists() else {}
    contracts, nodes = {}, []
    start, end = {}, {}
    for index, node in enumerate(flow["nodes"]):
        extra = extras.get(node["id"], {})
        labels = {item["path"]: item["label"] for item in extra.get("outputs", []) if "path" in item and "label" in item}
        contract = SkillContract(
            node_id=qualified_id(node), label=node["name"], group=node["stage"], skill=node["skill"],
            checkpoints=tuple(node["checkpoints"]), inputs=_input_specs(extra.get("inputs", [])),
            outputs=_output_specs(flow, node, labels), validators=tuple(extra.get("validators", [])),
            guards=tuple(extra.get("guards", [])), runtime_id=node["id"])
        contracts[node["skill"]] = contract
        nodes.append(_legacy_node(contract, extra, node.get("order", index)))
        for checkpoint in node["checkpoints"]:
            (end if checkpoint.endswith("_done") or checkpoint == "archived" else start)[checkpoint] = node["skill"]
    chain = list(flow["checkpoints"]["chain"])
    allowed = {checkpoint: frozenset(query.allowed_next(checkpoint)) for checkpoint in chain}
    return WorkflowContracts(
        nodes=tuple(nodes), profile=BASE_WORKFLOW_PROFILE, skill_contracts=contracts, known_checkpoints=frozenset(chain),
        initial_checkpoints=frozenset([flow["checkpoints"]["initial"]]), allowed_next=allowed,
        stage_labels={checkpoint: query.checkpoint_label(checkpoint) for checkpoint in chain},
        start_checkpoint_to_skill=start, end_checkpoint_to_skill=end)


def load_record_workflow_contracts(repo_root: Path | None = None, record: dict | None = None, *,
                                   workspace: Path | None = None, **_ignored) -> WorkflowContracts:
    """某个 Feature 的契约。v1 所有 Feature 都走同一条 standard 流程，与 load_repo_workflow_contracts 相同。"""
    return load_contracts()


def load_repo_workflow_contracts(repo_root: Path | None = None, *, workspace: Path | None = None,
                                 profile: str = BASE_WORKFLOW_PROFILE, **_ignored) -> WorkflowContracts:
    if profile not in (BASE_WORKFLOW_PROFILE, "base"):
        raise BoardConfigError(f"v1 只有 standard 流程，没有 profile {profile}")
    return load_contracts()


def configured_profile_names(_config: Any = None) -> tuple[str, ...]:
    return (BASE_WORKFLOW_PROFILE,)


def normalize_workflow_decisions(_value: Any = None) -> dict[str, str]:
    return {}


def load_board_config(_path: Path | None = None) -> dict:
    """原 board_config.json 的 workflow 部分（只含节点），供只读 workflow.nodes 的调用方使用。"""
    return {"workflow": {"nodes": [dict(node) for node in load_contracts().nodes]}}


def artifact_dicts(node: dict, direction: str = "outputs") -> list[dict]:
    artifacts = node.get("artifacts") or {}
    items = artifacts.get(direction) if isinstance(artifacts, dict) else None
    return [dict(item) for item in items or [] if isinstance(item, dict)]


def find_current_node(nodes, checkpoint: str, *_args, **_kwargs) -> tuple[int, str | None]:
    """checkpoint 所在的节点：(在 nodes 中的位置, 节点 id)；archived 算终态节点；找不到时为 (-1, None)。"""
    for index, node in enumerate(nodes):
        if checkpoint in node.get("checkpoints", []):
            return index, node.get("id")
    if checkpoint == "archived" and nodes:
        return len(nodes) - 1, nodes[-1].get("id")
    return -1, None


def find_effective_current_node(nodes, checkpoint: str, _needs_fix_from=None, **_kwargs) -> tuple[int, str | None]:
    """v1 没有 needs_fix，Feature 的当前节点就是 checkpoint 所在的节点。"""
    return find_current_node(nodes, checkpoint)
