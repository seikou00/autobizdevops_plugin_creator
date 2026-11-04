"""插件目录的只读视图，可以叠加内存中的修改（overlay）。

编辑命令先在内存中改好文件，再用叠加后的视图走 doctor 流水线，没有 error 才一起写盘（D56）。
overlay 中值为 None 的路径表示删除该文件。
"""

from __future__ import annotations

from pathlib import Path


class Tree:
    def __init__(self, root: Path, overlay: dict[str, bytes | None] | None = None):
        self.root = Path(root)
        self.overlay = dict(overlay or {})

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_bytes(self, rel: str) -> bytes | None:
        if rel in self.overlay:
            return self.overlay[rel]
        path = self.root / rel
        return path.read_bytes() if path.is_file() else None

    def is_file(self, rel: str) -> bool:
        if rel in self.overlay:
            return self.overlay[rel] is not None
        return (self.root / rel).is_file()

    def is_dir(self, rel: str) -> bool:
        prefix = rel.rstrip("/") + "/"
        if any(key.startswith(prefix) and data is None for key, data in self.overlay.items()):
            return bool(self.walk(rel))
        return (self.root / rel).is_dir() or any(key.startswith(prefix) for key in self.overlay)

    def list_dir(self, rel: str) -> list[str]:
        """rel 下一层的名字（文件和目录），按名字排序；被删光的子目录不再列出。"""
        names = set()
        path = self.root / rel
        if path.is_dir():
            names.update(child.name for child in path.iterdir())
        prefix = rel.rstrip("/") + "/" if rel else ""
        for key, data in self.overlay.items():
            if key.startswith(prefix) and data is not None:
                names.add(key[len(prefix):].split("/")[0])
        return sorted(name for name in names if self.is_file(prefix + name) or self.is_dir(prefix + name))

    def walk(self, rel: str) -> list[str]:
        """rel 下的全部文件，返回相对插件根的 POSIX 路径。"""
        result = set()
        base = self.root / rel
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_file():
                    result.add(path.relative_to(self.root).as_posix())
        prefix = rel.rstrip("/") + "/"
        for key, data in self.overlay.items():
            if key.startswith(prefix):
                (result.add if data is not None else result.discard)(key)
        return sorted(result)
