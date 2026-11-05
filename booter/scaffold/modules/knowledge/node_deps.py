"""collector（collect-knowledge.js）的 Node 依赖：doctor 写盘后在 runtime/knowledge/ 下执行 npm install（README §9 第 7 条）。

依赖列在同目录的 package.json 中；node_modules/ 不归 build-manifest 记录，package 时整个目录随包带上。
安装失败不挡住 doctor，只报 KNOWLEDGE_NODE_DEPS warning：会话中 collector 不可用时按清单映射加载知识。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from scaffold.lib.issues import warning

DIR = "runtime/knowledge"
PACKAGE_JSON = f"{DIR}/package.json"
NODE_MODULES = f"{DIR}/node_modules"
INSTALL_TIMEOUT = 300
SKIP_ENV = "AUTOBIZ_SKIP_NPM_INSTALL"
CODE = "KNOWLEDGE_NODE_DEPS"
FALLBACK = "会话中 collector 不可用，内置组装脚本会退回按清单映射加载知识"


def declared(root: Path) -> list:
    try:
        data = json.loads((root / PACKAGE_JSON).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    deps = data.get("dependencies") if isinstance(data, dict) else None
    return sorted(deps) if isinstance(deps, dict) else []


def missing(root: Path) -> list:
    return [name for name in declared(root) if not (root / NODE_MODULES / name / "package.json").is_file()]


def _hint(extra: str = "") -> str:
    return (f"{extra}在 {DIR}/ 下执行 npm install --omit=dev，或连上 npm 源后重新执行 autobiz-plugin doctor；"
            f"未安装时{FALLBACK}")


def _npm():
    # Windows 上 npm 是 npm.cmd，subprocess 不会自动补扩展名
    return shutil.which("npm") or shutil.which("npm.cmd")


def install(root: Path) -> tuple[bool, str]:
    """返回 (是否成功, 失败原因)。"""
    npm = _npm()
    if npm is None:
        return False, "PATH 中找不到 npm"
    command = [npm, "install", "--omit=dev", "--no-audit", "--no-fund", "--no-package-lock", "--loglevel=error"]
    try:
        completed = subprocess.run(command, cwd=str(root / DIR), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=INSTALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"npm install 超时（{INSTALL_TIMEOUT} 秒）"
    except OSError as error:
        return False, f"启动 npm 失败：{error}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode("utf-8", "replace").strip()
        lines = [line for line in detail.splitlines() if line.strip()][-5:]
        return False, f"npm install 失败（返回码 {completed.returncode}）" + ("：" + " / ".join(lines) if lines else "")
    return True, ""


def prepare(root: Path, *, install_missing: bool) -> list:
    absent = missing(root)
    if not absent:
        return []
    names = "、".join(absent)
    if not install_missing:
        return [warning(CODE, f"collector 依赖 {names} 没有安装，打包时不会带上", file=PACKAGE_JSON, hint=_hint())]
    if os.environ.get(SKIP_ENV):
        return [warning(CODE, f"设置了 {SKIP_ENV}，没有安装 collector 依赖 {names}", file=PACKAGE_JSON, hint=_hint())]
    ok, reason = install(root)
    absent = missing(root) if ok else absent
    if ok and not absent:
        return []
    reason = reason or f"npm install 之后仍缺少 {'、'.join(absent)}"
    return [warning(CODE, f"拉取 collector 依赖 {names} 失败：{reason}", file=PACKAGE_JSON,
                    hint=_hint("检查网络和 npm 源（npm config get registry）后，"))]
