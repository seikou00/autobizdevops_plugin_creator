"""初始化与状态变更：状态转移检查 → 产物存在性检查 →（_done 时）校验命令 → 加锁提交 → 变更日志。

不执行技能正文、不生成业务产物、不处理看板格式或会话提示词（interfaces.md §4.6）。
"""

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


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)  # Windows 上读方可能正短暂持有文件
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def state_lock(project_path):
    """锁住完整的“读取 → 校验 → 写入”事务，跨进程有效。"""
    directory = query.metadata_dir(project_path)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".state.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 5
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
                    raise BoardError("状态正在被其他进程更新，请稍后重试")
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def persist(project_path, payload):
    atomic_write(query.state_path(project_path), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def ensure_feature_files(project_path, feature):
    directory = query.feature_dir(project_path, feature)
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "hooks.ndjson"
    if not log.exists():
        log.touch()


def append_event(project_path, feature, event_id, status, message, **extra):
    event = {"ts": now(), "source": "hook", "pluginId": query.plugin_id(),
             "sessionId": os.environ.get("SESSION_ID", ""), "featureId": feature,
             "eventId": event_id, "eventStatus": status, "message": message, **extra}
    ensure_feature_files(project_path, feature)
    with (query.feature_dir(project_path, feature) / "hooks.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def init_project(project_path):
    with state_lock(project_path):
        created = not query.state_path(project_path).exists()
        payload = query.load_state(project_path)
        persist(project_path, payload)
        for feature in payload["features"]:
            ensure_feature_files(project_path, feature)
    return {"ok": True, "initialized": True, "created": created,
            "statePath": str(query.state_path(project_path)), "warnings": []}


def init_feature(project_path, feature, *, owner=None, iteration=None, template="standard"):
    if template != "standard":
        raise BoardError(f"v1 只支持 standard 模板: {template}")
    flow = query.load_flow()
    with state_lock(project_path):
        payload = query.load_state(project_path)
        record = payload["features"].get(feature)
        created = record is None
        if created:
            directory = query.feature_dir(project_path, feature)
            if directory.exists():
                raise BoardError(f"Feature 目录已存在但没有状态记录，请先核对已有产物: {directory}")
            checkpoint = flow["checkpoints"]["initial"]
            record = {"feature": feature, "owner": owner or "—", "iteration": iteration or "—",
                      "checkpoint": checkpoint, "stage": query.stage_label(checkpoint),
                      "workflowProfile": template, "workflowTemplate": template, "updated_at": now()}
            payload["features"][feature] = record
        persist(project_path, payload)
        ensure_feature_files(project_path, feature)
    return {"ok": True, "created": created, "checkpoint": record["checkpoint"],
            "statePath": str(query.state_path(project_path)),
            "featureDir": str(query.feature_dir(project_path, feature)), "warnings": []}


def check_artifacts(project_path, feature, node, directions):
    missing = []
    for direction in directions:
        for artifact in query.node_artifacts(node["id"], direction):
            presence = query.artifact_presence(project_path, feature, artifact["id"])
            missing.extend(f"{artifact['label']}（{pattern}）" for pattern in presence["missing"])
    if missing:
        raise BoardError("必需产物缺失: " + "、".join(missing))


def run_validate(project_path, feature, node):
    """按单行命令约定执行校验（interfaces.md §4.3、§4.4），返回 validation 结果。"""
    directory = query.feature_dir(project_path, feature)
    values = {"python": sys.executable, "pluginPath": str(query.ROOT),
              "skillPath": str(query.ROOT / "skills" / node["skill"]), "projectPath": str(project_path),
              "featureDir": str(directory), "feature": feature, "nodeId": node["id"]}
    args = []
    for arg in shlex.split(node["validate"]):
        for name, value in values.items():
            arg = arg.replace("${" + name + "}", value)
        args.append(arg)
    env = {**os.environ, "PLUGIN_ROOT": str(query.ROOT), "PROJECT_PATH": str(project_path),
           "FEATURE_DIR": str(directory), "FEATURE_ID": feature, "NODE_ID": node["id"],
           "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    timeout = query.load_runtime().get("validateTimeoutSec", 120)
    try:
        completed = subprocess.run(args, cwd=directory, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=timeout)
        exit_code, timed_out, raw = completed.returncode, False, completed.stdout
    except subprocess.TimeoutExpired as error:
        exit_code, timed_out, raw = None, True, error.stdout or b""
    except OSError as error:
        exit_code, timed_out, raw = None, False, f"校验命令无法启动: {error}".encode("utf-8")
    output = raw.decode("utf-8", errors="replace")[-OUTPUT_TAIL:]
    return {"ran": True, "passed": exit_code == 0, "exitCode": exit_code,
            "durationMs": int((time.monotonic() - started) * 1000), "timedOut": timed_out, "output": output}


def transition(project_path, feature, checkpoint, *, reopen=False, reason="", dry_run=False,
               owner=None, iteration=None, _skip_validate=False):
    """_skip_validate 只供 simulate 在进程内调用，命令行入口不暴露。"""
    index, node, status = query.locate(checkpoint)

    def run():
        payload = query.load_state(project_path)
        record = payload["features"].get(feature)
        if record is None:
            raise BoardError(f"Feature 不存在，请先创建: {feature}")
        old = record["checkpoint"]
        old_index, _, _ = query.locate(old)
        chain = query.checkpoint_chain()
        if reopen:
            if status != "in_progress" or index > old_index or not (reason or "").strip():
                raise BoardError("重开只能回到当前或之前节点的 _in_progress，并必须提供 --reason")
        elif checkpoint != old and chain.index(checkpoint) != chain.index(old) + 1:
            raise BoardError(f"不允许状态跳转: {old} → {checkpoint}")
        changed = checkpoint != old or reopen or any(
            value is not None and value != record.get(key) for key, value in (("owner", owner), ("iteration", iteration)))
        result = {"ok": True, "changed": changed, "feature": feature, "oldCheckpoint": old,
                  "checkpoint": checkpoint, "statePath": str(query.state_path(project_path)),
                  "dryRun": dry_run, "warnings": []}
        if not changed:
            return result
        check_artifacts(project_path, feature, node, ["inputs"] if status == "in_progress" else ["inputs", "outputs"])
        if status == "done" and not reopen and checkpoint != old and node.get("validate"):
            if _skip_validate:
                result["warnings"].append("simulate 跳过了校验命令")
            else:
                validation = run_validate(project_path, feature, node)
                result["validation"] = validation
                if not dry_run:
                    append_event(project_path, feature, "node-validate", "success" if validation["passed"] else "failed",
                                 f"{node['id']} 校验{'通过' if validation['passed'] else '未通过'}",
                                 nodeId=node["id"], exitCode=validation["exitCode"],
                                 durationMs=validation["durationMs"], timedOut=validation["timedOut"])
                if not validation["passed"]:
                    why = "超时" if validation["timedOut"] else f"退出码 {validation['exitCode']}"
                    raise BoardError(f"{node['id']} 的校验命令未通过（{why}）:\n{validation['output']}")
        if dry_run:
            return result
        updated = copy.deepcopy(payload)
        target = updated["features"][feature]
        target.update(checkpoint=checkpoint, stage=query.stage_label(checkpoint), updated_at=now())
        for key, value in (("owner", owner), ("iteration", iteration)):
            if value is not None:
                target[key] = value
        persist(project_path, updated)
        try:
            append_event(project_path, feature, "update-state", "success", reason or f"{old} → {checkpoint}",
                         **{"from": old, "to": checkpoint, "nodeId": node["id"], "reopen": reopen})
        except OSError as error:
            result["warnings"].append(f"状态已保存，变更日志未写入: {error}")
        return result

    if dry_run:
        return run()
    with state_lock(project_path):
        return run()
