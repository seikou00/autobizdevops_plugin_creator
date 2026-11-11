"""Feature 状态的读取与变更（取代原插件的 board_core.state_store）。

状态文件 <metaRoot>/state.json 归运行框架所有：读取用 runtime.common.query，变更只走 runtime.common.engine
（加锁、boardSeq、看板事件、变更日志都在那里），流程脚本不再直接写这个文件，也不再生成 STATE.md。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from runtime.common import engine, query  # noqa: E402

StateRecords = dict  # Feature → 状态记录


@dataclass
class StateLoadResult:
    exists: bool
    records: StateRecords = field(default_factory=dict)
    fatal_errors: list[str] = field(default_factory=list)
    record_errors: dict[str, list[str]] = field(default_factory=dict)
    raw_records: dict[str, Any] = field(default_factory=dict)
    source: str = "state.json"

    # 原 check_or_fix_state_sync 结果的字段名
    @property
    def state_exists(self) -> bool:
        return self.exists

    @property
    def errors(self) -> list[str]:
        return self.fatal_errors

    @property
    def state_json_path(self) -> str:
        return ""


def get_state_json_path(workspace: Path) -> Path:
    return query.state_path(Path(workspace))


def load_state_json_records_result(workspace: Path) -> StateLoadResult:
    path = get_state_json_path(workspace)
    if not path.exists():
        return StateLoadResult(exists=False)
    try:
        payload = query.load_state(Path(workspace))
    except query.BoardError as error:
        return StateLoadResult(exists=True, fatal_errors=[str(error)])
    records = {name: dict(record) for name, record in payload["features"].items()}
    return StateLoadResult(exists=True, records=records, raw_records={name: dict(record) for name, record in records.items()})


def check_or_fix_state_sync(workspace: Path, *, fix: bool = True) -> StateLoadResult:
    """运行框架只有 state.json，没有要同步的 STATE.md：等同于读取状态。"""
    return load_state_json_records_result(workspace)


def find_feature_dir(workspace: Path, feature: str, *_args, **_kwargs) -> Path | None:
    directory = query.feature_dir(Path(workspace), feature)
    return directory if directory.is_dir() else None


def reopen(workspace: Path, feature: str, checkpoint: str, *, reason: str, dry_run: bool = False) -> dict:
    """把 Feature 重开到当前或之前某个节点的 _in_progress（阶段回退用），由运行框架检查并提交。"""
    try:
        return engine.transition(Path(workspace), feature, checkpoint, reopen=True, reason=reason, dry_run=dry_run)
    except query.BoardError as error:
        raise ValueError(str(error)) from None
