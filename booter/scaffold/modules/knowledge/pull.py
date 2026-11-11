"""声明 knowledge.source 时，doctor 写盘后执行一次 sync_knowledge.py，把知识仓库拉到插件的 sys/。

只在 sys/ 中还没有清单时拉取：check、simulate 的契约测试会复制 sys/，有了清单 deploy_units 才不报
KNOWLEDGE_MANIFEST_MISSING。sys/ 不随包带上（运行时由 DevClaw 调用 pull_knowledge），这里只服务本地校验。
拉取失败不挡住 doctor，只报 KNOWLEDGE_PULL warning。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scaffold.lib.issues import warning

SCRIPT = "runtime/knowledge/sync_knowledge.py"
KNOWLEDGE_ROOT = "sys"
DEFAULT_MANIFEST = "agents.manifest.json"
TIMEOUT = 300
SKIP_ENV = "AUTOBIZ_SKIP_KNOWLEDGE_PULL"
CODE = "KNOWLEDGE_PULL"
HINT = (f"检查网络、仓库权限和 source.ref 后重新执行 autobiz-plugin doctor，或在插件目录执行 python3 {SCRIPT}；"
        "不影响打包，运行时由 DevClaw 调用 pull_knowledge 拉取")


def run(root: Path) -> tuple[bool, str]:
    """返回 (是否成功, 失败原因)。"""
    try:
        completed = subprocess.run([sys.executable, str(root / SCRIPT)], cwd=str(root), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"超时（{TIMEOUT} 秒）"
    except OSError as error:
        return False, f"启动 Python 失败：{error}"
    try:
        payload = json.loads(completed.stdout.decode("utf-8", "replace"))
    except ValueError:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        return False, "输出不是合法 JSON" + ("：" + " / ".join(detail) if detail else "")
    if payload.get("ok") is False:
        return False, "；".join(payload.get("errors") or [payload.get("message") or "未知错误"])
    return True, ""


def prepare(root: Path, options: dict, *, install: bool) -> list:
    if not install or options.get("source") is None or os.environ.get(SKIP_ENV):
        return []
    manifest = (options.get("manifest") or {}).get("path") or DEFAULT_MANIFEST
    if (root / KNOWLEDGE_ROOT / manifest).is_file() or not (root / SCRIPT).is_file():
        return []
    ok, reason = run(root)
    if ok:
        return []
    return [warning(CODE, f"拉取知识仓库失败：{reason}", file="modules/knowledge.json", pointer="/source", hint=HINT)]
