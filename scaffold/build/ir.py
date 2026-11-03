"""模块看到的流程：只包含核心流程和入口文件的信息（scaffold.md 单元 5，D49）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str                      # 输出路径原文（D39）
    paths: tuple                    # v1 只有一项
    type: str                       # "file" | "json"
    producer: str                   # 第一个输出它的节点 id


@dataclass(frozen=True)
class OutputRef:
    artifact: str
    required: bool


@dataclass(frozen=True)
class NodeIR:
    id: str
    name: str
    stage: str                      # "Biz" | "Dev" | "Ops"；分组键用 stage.lower()
    seq: int
    order: int                      # 按 seq 排列后的位置 (i + 1) * 10
    skill: str
    description: str                # SKILL.md 的 description；缺省或仍是 [TODO] 时按 input-config.md §6 推导
    terminal: bool
    outputs: tuple                  # OutputRef
    inputs: tuple = ()              # v1 恒为空（D32）
    validate: Optional[str] = None  # v1 恒为 None（D32）

    @property
    def group(self) -> str:
        return self.stage.lower()

    @property
    def checkpoints(self) -> tuple:
        return ("archived",) if self.terminal else (f"{self.id}_in_progress", f"{self.id}_done")


@dataclass(frozen=True)
class PluginIR:
    plugin: dict
    runtime: dict
    stages: tuple
    nodes: tuple
    artifacts: dict                 # 产物 id → ArtifactIR，按首次出现的顺序
    checkpoint_chain: tuple

    def node(self, node_id: str) -> NodeIR:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def has_node(self, node_id: str) -> bool:
        return any(node.id == node_id for node in self.nodes)

    def next_node(self, node_id: str) -> Optional[NodeIR]:
        ids = [node.id for node in self.nodes]
        index = ids.index(node_id)
        return self.nodes[index + 1] if index + 1 < len(self.nodes) else None

    def anchor_checkpoint(self, anchor: str) -> Optional[str]:
        """"<nodeId>:<in_progress|done>"、"<nodeId>"（取开始 checkpoint）或 checkpoint 名 → checkpoint。"""
        if ":" in anchor:
            node_id, state = anchor.split(":", 1)
            if not self.has_node(node_id):
                return None
            node = self.node(node_id)
            if node.terminal:
                return "archived"
            return f"{node_id}_{state}"
        if anchor in self.checkpoint_chain:
            return anchor
        if self.has_node(anchor):
            return self.node(anchor).checkpoints[0]
        return None

    def checkpoints_from(self, anchor: str) -> tuple:
        checkpoint = self.anchor_checkpoint(anchor)
        if checkpoint is None or checkpoint not in self.checkpoint_chain:
            return ()
        return self.checkpoint_chain[self.checkpoint_chain.index(checkpoint):]
