"""框架入口共用：stdout 只输出一个 UTF-8 JSON 对象，业务失败以 1 退出（interfaces.md §3.1）。"""

import json
import sys

from .query import BoardError


def emit(payload):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def execute(action):
    try:
        emit(action())
        return 0
    except (BoardError, OSError, KeyError) as error:
        emit({"ok": False, "errors": [str(error)]})
        return 1
