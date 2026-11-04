"""初始化与状态变更（interfaces.md §4.2–§4.6，output-spec.md §4）。

所有写入都在 .state.lock 内完成“读取 → 校验 → 原子替换”；提交时把 boardSeq 加 1 并在返回值中给出，
由入口在释放锁之后推送看板事件（interfaces.md §3.5.3）。engine 不处理看板格式。
"""

from __future__ import annotations

import copy
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import query
from .query import BoardError

OUTPUT_TAIL = 2000


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def session_id() -> str:
    return os.environ.get("SESSION_ID") or os.environ.get("session_id") or ""


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def file_lock(path: Path, timeout: float = 5.0):
    """跨进程锁：POSIX 用 flock，Windows 用 msvcrt.locking（沿用 lite）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise BoardError("状态正在被其他进程更新，请稍后重试") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def state_lock(project_path: Path):
    query.metadata_dir(project_path).mkdir(parents=True, exist_ok=True)
    with file_lock(query.lock_path(project_path)):
        yield


def _drop_history(payload: dict) -> None:
    for record in payload["features"].values():
        record.pop("history", None)


def _commit(project_path: Path, payload: dict) -> int:
    path = query.state_path(project_path)
    if payload.pop(query.MIGRATED_FROM, None):
        # 第一次写入全栈版 v3 状态：先备份原文件，再升级为 schemaVersion 1（D60）
        backup = path.with_name("state.v3.bak.json")
        if path.exists() and not backup.exists():
            atomic_write(backup, path.read_text(encoding="utf-8-sig"))
    payload["boardSeq"] = int(payload.get("boardSeq", 0)) + 1
    _drop_history(payload)
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload["boardSeq"]


def append_event(project_path: Path, feature: str, event_id: str, status: str, message: str, **extra) -> None:
    event = {"ts": now(), "source": "hook", "pluginId": query.plugin_id(), "sessionId": session_id(),
             "featureId": feature, "eventId": event_id, "eventStatus": status, "message": message, **extra}
    path = query.hook_log_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _log(project_path: Path, warnings: list, *args, **kwargs) -> None:
    try:
        append_event(project_path, *args, **kwargs)
    except OSError as error:
        warnings.append(f"状态已保存，变更日志未写入: {error}")


# —— 初始化 ——

def init_project(project_path: Path) -> dict:
    with state_lock(project_path):
        created = not query.state_path(project_path).exists()
        payload = query.load_state(project_path)
        seq = _commit(project_path, payload)
    return {"ok": True, "initialized": True, "created": created, "statePath": str(query.state_path(project_path)),
            "warnings": [], "boardSeq": seq}


def _deploy_units(units) -> list:
    result = []
    for unit in units or []:
        if not isinstance(unit, dict) or not unit.get("deployUnitId"):
            raise BoardError(f"发布单元缺少 deployUnitId: {unit!r}")
        result.append({"deployUnitId": unit["deployUnitId"], "localRepoPath": unit.get("localRepoPath", "")})
    return result


def init_feature(project_path: Path, feature: str, *, owner: str | None = None, iteration: str | None = None,
                 template: str = "standard", deploy_units=None) -> dict:
    query.safe_component(feature, "Feature ")
    if template != "standard":
        raise BoardError(f"v1 只支持 standard 模板: {template}")
    flow = query.load_flow()
    with state_lock(project_path):
        payload = query.load_state(project_path)
        record = payload["features"].get(feature)
        created = record is None
        if record is not None and query.is_stranded(record) and deploy_units is not None:
            raise BoardError(query.stranded_reason(record))
        if created:
            directory = query.feature_dir(project_path, feature)
            if directory.exists():
                raise BoardError(f"Feature 目录已存在但 state.json 中没有记录，请先核对已有产物: {directory}")
            checkpoint = flow["checkpoints"]["initial"]
            record = {"feature": feature, "owner": owner or "—", "iteration": iteration or "—",
                      "checkpoint": checkpoint, "stage": query.checkpoint_label(checkpoint),
                      "workflowProfile": "standard", "workflowTemplate": "standard"}
            payload["features"][feature] = record
        if deploy_units is not None:
            record["deployUnits"] = _deploy_units(deploy_units)
        if created or deploy_units is not None:
            record["updated_at"] = now()
        query.feature_dir(project_path, feature).mkdir(parents=True, exist_ok=True)
        seq = _commit(project_path, payload)
    return {"ok": True, "created": created, "checkpoint": record["checkpoint"],
            "statePath": str(query.state_path(project_path)),
            "featureDir": str(query.feature_dir(project_path, feature)), "warnings": [], "boardSeq": seq}


# —— 状态变更 ——

def check_artifacts(project_path: Path, feature: str, refs: list) -> list:
    problems = []
    for ref in refs:
        if not ref.get("required", True):
            continue
        presence = query.artifact_presence(project_path, feature, ref["id"])
        for pattern in presence["missing"]:
            problems.append(f"必需产物缺失: {pattern}")
        for path in presence["empty"]:
            problems.append(f"必需产物为空: {query.relative_to_project(query.feature_dir(project_path, feature), path)}")
    return problems


def _placeholders(project_path: Path, feature: str, node: dict) -> dict:
    return {"python": sys.executable, "pluginPath": str(query.plugin_root()),
            "skillPath": str(query.plugin_root() / node["skillDir"]), "projectPath": str(project_path),
            "featureDir": str(query.feature_dir(project_path, feature)), "feature": feature, "nodeId": node["id"]}


def run_validate(project_path: Path, feature: str, node: dict) -> dict:
    """单行命令：先 shlex 拆分，再逐个参数替换占位符，不经过 shell（interfaces.md §4.3、§4.4）。"""
    values = _placeholders(project_path, feature, node)
    argv = []
    for arg in shlex.split(node["validate"]):
        for key, value in values.items():
            arg = arg.replace("${" + key + "}", value)
        argv.append(arg)
    env = {**os.environ, "PLUGIN_ROOT": values["pluginPath"], "PROJECT_PATH": values["projectPath"],
           "FEATURE_DIR": values["featureDir"], "FEATURE_ID": feature, "NODE_ID": node["id"],
           "PYTHONIOENCODING": "utf-8"}
    timeout = query.runtime_config().get("validateTimeoutSec", 120)
    started = time.monotonic()
    try:
        completed = subprocess.run(argv, cwd=values["featureDir"], env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=timeout)
        code, timed_out, output = completed.returncode, False, completed.stdout
    except subprocess.TimeoutExpired as expired:
        code, timed_out, output = None, True, expired.stdout or b""
    except OSError as error:
        code, timed_out, output = None, False, str(error).encode("utf-8")
    text = output.decode("utf-8", "replace")[-OUTPUT_TAIL:]
    return {"ran": True, "passed": code == 0, "exitCode": code, "durationMs": int((time.monotonic() - started) * 1000),
            "timedOut": timed_out, "output": text}


def _prepare(project_path: Path, payload: dict, feature: str, checkpoint: str, *, reopen: bool, reason: str):
    record = payload["features"].get(feature)
    if record is None:
        raise BoardError(f"Feature 不存在，请先创建: {feature}")
    if query.is_stranded(record):
        raise BoardError(query.stranded_reason(record))
    index, node, status = query.locate(checkpoint)
    old = record["checkpoint"]
    old_index, _, old_status = query.locate(old)
    if old_status == "archived" and checkpoint != old:
        raise BoardError("Feature 已归档，不能再推进或重开")
    if reopen:
        if status != "in_progress" or index > old_index or not (reason or "").strip():
            raise BoardError("重开只能回到当前或之前节点的 _in_progress，并且必须提供非空的 --reason")
    elif checkpoint != old and checkpoint not in query.allowed_next(old):
        allowed = "、".join(query.allowed_next(old)) or "无（流程已结束）"
        raise BoardError(f"不允许状态跳转: {old} → {checkpoint}；当前允许: {old} 或 {allowed}")
    # 产物存在且非空只提醒、不阻止推进；拦截由宿主钩子 hooks/artifact_guard.py 在执行完成命令前完成
    problems = check_artifacts(project_path, feature, node.get("inputs", []))
    if status == "done" and checkpoint != old:
        problems += check_artifacts(project_path, feature, node.get("outputs", []))
    return node, status, old, problems


def transition(project_path: Path, feature: str, checkpoint: str, *, reopen: bool = False, reason: str = "",
               dry_run: bool = False, owner: str | None = None, iteration: str | None = None) -> dict:
    """状态转移检查（含 archived）→ 产物存在且非空（只提醒）→ （_done 且 validate 不为 null 时）校验命令 → 加锁提交
    → 变更日志。"""
    query.safe_component(feature, "Feature ")

    def evaluate(payload):
        node, status, old, problems = _prepare(project_path, payload, feature, checkpoint, reopen=reopen, reason=reason)
        result["warnings"] += [f"推进到 {checkpoint} 时{problem}" for problem in problems]
        validation = None
        if status == "done" and checkpoint != old and not reopen and node.get("validate"):
            validation = run_validate(project_path, feature, node)
        return node, old, validation, problems

    result = {"ok": True, "changed": False, "feature": feature, "statePath": str(query.state_path(project_path)),
              "dryRun": dry_run, "warnings": []}
    if dry_run:
        node, old, validation, _ = evaluate(query.load_state(project_path))
        if validation is not None and not validation["passed"]:
            why = "超时" if validation["timedOut"] else f"退出码 {validation['exitCode']}"
            raise BoardError(f"{node['id']} 的校验命令未通过（{why}）:\n{validation['output']}")
        result.update(oldCheckpoint=old, checkpoint=checkpoint, changed=checkpoint != old or reopen)
        return _with_validation(result, node, validation)
    with state_lock(project_path):
        payload = query.load_state(project_path)
        node, old, validation, problems = evaluate(payload)
        if validation is not None:
            _log(project_path, result["warnings"], feature, "node-validate", "success" if validation["passed"] else "failed",
                 f"{node['id']} 的校验命令" + ("通过" if validation["passed"] else "未通过"), nodeId=node["id"],
                 exitCode=validation["exitCode"], durationMs=validation["durationMs"], timedOut=validation["timedOut"])
            if not validation["passed"]:
                why = "超时" if validation["timedOut"] else f"退出码 {validation['exitCode']}"
                raise BoardError(f"{node['id']} 的校验命令未通过（{why}）:\n{validation['output']}")
        record = payload["features"][feature]
        changed = checkpoint != old or reopen or any(value is not None and record.get(key) != value
                                                     for key, value in (("owner", owner), ("iteration", iteration)))
        result.update(oldCheckpoint=old, checkpoint=checkpoint, changed=changed)
        if changed:
            updated = copy.deepcopy(payload)
            target = updated["features"][feature]
            target.update(checkpoint=checkpoint, stage=query.checkpoint_label(checkpoint), updated_at=now())
            for key, value in (("owner", owner), ("iteration", iteration)):
                if value is not None:
                    target[key] = value
            result["boardSeq"] = _commit(project_path, updated)
            if problems:
                _log(project_path, result["warnings"], feature, "artifact-check", "warning",
                     f"{node['id']} 的必需产物缺失或为空，仍然推进", nodeId=node["id"], problems=problems)
            if checkpoint != old or reopen:
                _log(project_path, result["warnings"], feature, "update-state", "success",
                     reason or f"{old} → {checkpoint}", **{"from": old, "to": checkpoint, "nodeId": node["id"],
                                                          "reopen": reopen})
    return _with_validation(result, node, validation)


def _with_validation(result: dict, node: dict, validation) -> dict:
    if validation is not None:
        result["validation"] = validation
    return result
