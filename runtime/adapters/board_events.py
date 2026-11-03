"""写入口提交后把看板数据推送给 DevClaw 的本机服务（interfaces.md §3.5，D21）。

只尝试一次，超时 300 ms，不重试；失败只在 stderr 写一行警告，命令的 stdout 和退出码不受影响。
必须在释放 .state.lock 之后调用。只用标准库 socket，并且只在设置了端点时才导入。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ENV = "AUTOBIZ_BOARD_ENDPOINT"
SCHEMA = "autobiz.board-events.v1"
TIMEOUT = 0.3
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _warn(message: str) -> None:
    try:
        sys.stderr.write(f"[board-events] {message}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def endpoint():
    """返回 (host, port, path)；未设置时返回 None，不合法时警告后返回 None。"""
    value = os.environ.get(ENV, "").strip()
    if not value:
        return None
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        port = None
        parts = None
    if parts is None or parts.scheme != "http" or parts.hostname not in LOOPBACK or port is None:
        _warn(f"{ENV} 只接受 http、回环地址和显式端口，已跳过推送: {value}")
        return None
    return parts.hostname, port, (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def build_params(project_path: Path, feature, reason: str, seq: int) -> dict:
    from runtime.adapters import board_view
    from runtime.common import query

    project_path = Path(project_path).resolve()
    return {
        "schema": SCHEMA, "pluginId": query.plugin_id(), "pluginPath": str(query.plugin_root().resolve()),
        "pluginWorkspace": str(project_path.parent), "projectDir": project_path.name,
        "seq": seq, "reason": reason, "sessionId": os.environ.get("SESSION_ID", ""),
        "feature": feature,
        "projectRuns": board_view.project_runs(project_path)["runs"],
        "run": board_view.run_payload(project_path, feature) if feature else None,
    }


def send(target, body: bytes) -> None:
    import socket

    host, port, path = target
    request = (f"POST {path} HTTP/1.1\r\nHost: {host}:{port}\r\nContent-Type: application/json\r\n"
               f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii") + body
    with socket.create_connection((host, port), timeout=TIMEOUT) as connection:
        connection.settimeout(TIMEOUT)
        connection.sendall(request)
        status = connection.recv(64).split(b"\r\n", 1)[0]
    if not status.startswith(b"HTTP/1.") or not status[9:10] == b"2":
        raise OSError(f"服务返回 {status.decode('latin-1', 'replace')}")


def push(project_path, feature, reason: str, seq) -> None:
    """尽力而为地推送一条 board/changed；任何错误都不影响调用方。"""
    if seq is None:
        return
    target = endpoint()
    if target is None:
        return
    try:
        message = {"jsonrpc": "2.0", "method": "board/changed",
                   "params": build_params(project_path, feature, reason, seq)}
        send(target, json.dumps(message, ensure_ascii=False).encode("utf-8"))
    except Exception as error:  # noqa: BLE001 - 推送失败不能影响命令结果
        _warn(f"看板事件推送失败（不影响本次操作）: {error}")
