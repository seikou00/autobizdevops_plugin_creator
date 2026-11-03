"""脚手架自带的资源：runtime/、schemas/、模块包文件和 new 的种子。

在仓库中运行时从仓库根目录读取；打成 autobiz-plugin.pyz 后从包内的 scaffold/_data/ 读取（D57），
两种情况都通过 importlib.resources 访问，不依赖 __file__ 能否打开。
"""

from __future__ import annotations

import importlib.resources
from functools import lru_cache


@lru_cache(maxsize=None)
def _base():
    package = importlib.resources.files("scaffold")
    data = package / "_data"
    if data.is_dir():
        return data
    return package.parent if hasattr(package, "parent") else package / ".."


def _node(rel: str):
    """"scaffold/…" 相对脚手架包本身（模块包的 files/ 等）；其余相对仓库根目录或包内的 _data/。"""
    rel = rel.strip("/")
    if rel == "scaffold" or rel.startswith("scaffold/"):
        node = importlib.resources.files("scaffold")
        rel = rel[len("scaffold"):]
    else:
        node = _base()
    for part in rel.strip("/").split("/"):
        if part:
            node = node / part
    return node


def exists(rel: str) -> bool:
    node = _node(rel)
    return node.is_file() or node.is_dir()


def read_bytes(rel: str) -> bytes:
    node = _node(rel)
    if not node.is_file():
        raise FileNotFoundError(f"脚手架资源不存在: {rel}")
    return node.read_bytes()


def read_text(rel: str) -> str:
    return read_bytes(rel).decode("utf-8")


def list_files(rel: str) -> list[str]:
    """rel 目录下的全部文件（递归），返回相对 rel 的 POSIX 路径，按路径排序；跳过缓存文件。"""
    result = []

    def walk(node, prefix):
        for child in node.iterdir():
            name = child.name
            if name in ("__pycache__", ".DS_Store", "Thumbs.db") or name.endswith(".pyc"):
                continue
            if child.is_dir():
                walk(child, f"{prefix}{name}/")
            else:
                result.append(f"{prefix}{name}")

    node = _node(rel)
    if node.is_dir():
        walk(node, "")
    return sorted(result)
