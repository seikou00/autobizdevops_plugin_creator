"""文件读写与摘要（scaffold.md 单元 1，D42、D43）。

- 读：一律 UTF-8，接受 BOM；JSON 中的重复键报错；
- 写：按字节写入，固定为 LF，不带 BOM，同目录临时文件 + os.replace；
- 摘要：sha256:<hex>，文本文件先把 CRLF 换成 LF。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class JsonError(ValueError):
    def __init__(self, path: str, line: int, column: int, message: str):
        super().__init__(message)
        self.path = path
        self.line = line
        self.column = column
        self.message = message

    def describe(self) -> str:
        if self.line:
            return f"第 {self.line} 行第 {self.column} 列：{self.message}"
        return self.message


class _DuplicateKey(ValueError):
    pass


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def decode(data: bytes) -> str:
    return data.decode("utf-8-sig")


def parse_json(data: bytes | str, path: str = "") -> object:
    try:
        text = decode(data) if isinstance(data, bytes) else data
    except UnicodeDecodeError as error:
        raise JsonError(path, 0, 0, f"不是 UTF-8 编码：{error}") from None
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates)
    except _DuplicateKey as error:
        raise JsonError(path, 0, 0, f"出现重复的键 {error.args[0]!r}，只能写一次") from None
    except json.JSONDecodeError as error:
        raise JsonError(path, error.lineno, error.colno, f"不是合法的 JSON：{error.msg}") from None


def read_json(path: Path) -> object:
    return parse_json(Path(path).read_bytes(), str(path))


def dump_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def is_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def normalized(data: bytes) -> bytes:
    """比较与摘要用的内容：文本文件把 CRLF 换成 LF（D42）。"""
    return data.replace(b"\r\n", b"\n") if is_text(data) else data


def digest(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(normalized(data)).hexdigest()


def same_content(a: bytes | None, b: bytes | None) -> bool:
    if a is None or b is None:
        return a is b
    return normalized(a) == normalized(b)


def atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
