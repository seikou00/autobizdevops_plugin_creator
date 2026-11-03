"""入口共用：stdout 只输出一个 UTF-8 JSON 对象，业务失败以 1 退出（interfaces.md §3.1，D59）。"""

from __future__ import annotations

import argparse
import json
import sys

from .query import BoardError


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()


def warn(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


class ArgumentParser(argparse.ArgumentParser):
    """参数错误也按协议输出 JSON，而不是 argparse 的用法文本。"""

    def error(self, message):
        raise BoardError(f"参数错误: {message}")


def run(action, *, always_zero: bool = False) -> int:
    """执行 action()，输出它返回的 JSON；BoardError 等转成 {"ok": false, "errors": [...]}。"""
    configure_stdio()
    try:
        payload = action()
    except (BoardError, OSError, KeyError, ValueError) as error:
        payload = {"ok": False, "errors": [str(error)]}
    emit(payload)
    if always_zero:
        return 0
    return 0 if payload.get("ok", True) else 1
