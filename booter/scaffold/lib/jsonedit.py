"""在原文上修改 JSON，保留原有键序、缩进和换行（scaffold.md 单元 12，Q12.3）。

只需要三种操作：往数组中插入一项、对象中增加或替换一个键、删除对象中的一个键。
只改动涉及的片段，其余字节不变；新内容的写法跟随同级元素（多行还是单行、缩进单位），换行符沿用原文件（D42）。
标准库的 json 不给出位置，所以这里实现一个记录位置的小型解析器。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_WS = " \t\r\n"


class EditError(ValueError):
    pass


@dataclass
class Node:
    kind: str                    # object | array | value
    start: int
    end: int                     # 不含
    members: list = field(default_factory=list)   # object: [(key, member_start, Node)]
    items: list = field(default_factory=list)     # array: [Node]


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in _WS:
            self.pos += 1

    def parse(self) -> Node:
        self.ws()
        if self.text.startswith("﻿", self.pos):
            self.pos += 1
            self.ws()
        node = self.value()
        self.ws()
        if self.pos != len(self.text):
            raise EditError(f"第 {self.pos} 个字符之后还有多余内容")
        return node

    def value(self) -> Node:
        if self.pos >= len(self.text):
            raise EditError("JSON 不完整")
        char = self.text[self.pos]
        if char == "{":
            return self.obj()
        if char == "[":
            return self.arr()
        start = self.pos
        if char == '"':
            self.string()
        elif self.text.startswith(("true", "false", "null"), self.pos):
            self.pos += 4 if self.text[self.pos] in "tn" else 5
        else:
            match = _NUMBER.match(self.text, self.pos)
            if not match:
                raise EditError(f"第 {self.pos} 个字符不是合法的 JSON 值")
            self.pos = match.end()
        return Node("value", start, self.pos)

    def string(self) -> str:
        start = self.pos
        self.pos += 1
        while True:
            if self.pos >= len(self.text):
                raise EditError("字符串没有结束")
            char = self.text[self.pos]
            if char == "\\":
                self.pos += 2
            elif char == '"':
                self.pos += 1
                return json.loads(self.text[start:self.pos])
            else:
                self.pos += 1

    def obj(self) -> Node:
        node = Node("object", self.pos, 0)
        self.pos += 1
        self.ws()
        if self.text.startswith("}", self.pos):
            self.pos += 1
            node.end = self.pos
            return node
        while True:
            self.ws()
            member_start = self.pos
            key = self.string()
            self.ws()
            if not self.text.startswith(":", self.pos):
                raise EditError(f"第 {self.pos} 个字符处缺少冒号")
            self.pos += 1
            self.ws()
            node.members.append((key, member_start, self.value()))
            self.ws()
            if self.text.startswith(",", self.pos):
                self.pos += 1
                continue
            if self.text.startswith("}", self.pos):
                self.pos += 1
                node.end = self.pos
                return node
            raise EditError(f"第 {self.pos} 个字符处缺少逗号或右花括号")

    def arr(self) -> Node:
        node = Node("array", self.pos, 0)
        self.pos += 1
        self.ws()
        if self.text.startswith("]", self.pos):
            self.pos += 1
            node.end = self.pos
            return node
        while True:
            self.ws()
            node.items.append(self.value())
            self.ws()
            if self.text.startswith(",", self.pos):
                self.pos += 1
                continue
            if self.text.startswith("]", self.pos):
                self.pos += 1
                node.end = self.pos
                return node
            raise EditError(f"第 {self.pos} 个字符处缺少逗号或右方括号")


def parse(text: str) -> Node:
    return _Parser(text).parse()


def _tokens(pointer: str) -> list:
    if pointer in ("", "/"):
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.lstrip("/").split("/")]


def locate(root: Node, pointer: str) -> Node:
    node = root
    for token in _tokens(pointer):
        if node.kind == "object":
            match = next((child for key, _, child in node.members if key == token), None)
        elif node.kind == "array" and token.isdigit() and int(token) < len(node.items):
            match = node.items[int(token)]
        else:
            match = None
        if match is None:
            raise EditError(f"找不到 {pointer}")
        node = match
    return node


# —— 排版 ——

def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def indent_unit(text: str) -> str:
    sizes = [len(line) - len(line.lstrip(" ")) for line in text.splitlines() if line.strip() and line.startswith(" ")]
    return " " * (min(sizes) if sizes else 2)


def line_indent(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    line = text[start:offset]
    return line[:len(line) - len(line.lstrip(" \t"))]


def is_multiline(text: str, node: Node) -> bool:
    return "\n" in text[node.start:node.end]


def _scalar(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _inline(value, *, spaced: bool) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        body = ", ".join(f"{_scalar(key)}: {_inline(item, spaced=spaced)}" for key, item in value.items())
        return f"{{ {body} }}" if spaced else f"{{{body}}}"
    if isinstance(value, list):
        return "[" + ", ".join(_inline(item, spaced=spaced) for item in value) + "]"
    return _scalar(value)


def render(value, indent: str, unit: str, nl: str) -> str:
    """多行写法：对象逐个键换行；只含标量的数组写在一行（与示例的手排格式一致）。"""
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = indent + unit
        lines = [f"{inner}{_scalar(key)}: {render(item, inner, unit, nl)}" for key, item in value.items()]
        return "{" + nl + ("," + nl).join(lines) + nl + indent + "}"
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return "[" + ", ".join(_scalar(item) for item in value) + "]"
        inner = indent + unit
        return "[" + nl + ("," + nl).join(inner + render(item, inner, unit, nl) for item in value) + nl + indent + "]"
    return _scalar(value)


def _render_like(text: str, sibling: Node | None, value, indent: str) -> str:
    unit, nl = indent_unit(text), newline_of(text)
    if sibling is not None and not is_multiline(text, sibling) and isinstance(value, (dict, list)):
        return _inline(value, spaced=text[sibling.start:sibling.start + 2] in ("{ ", "[ "))
    return render(value, indent, unit, nl)


# —— 操作 ——

def insert_item(text: str, pointer: str, index: int, value) -> str:
    root = parse(text)
    node = locate(root, pointer)
    if node.kind != "array":
        raise EditError(f"{pointer} 不是数组")
    unit, nl = indent_unit(text), newline_of(text)
    items = node.items
    index = max(0, min(index, len(items)))
    if not items:
        indent = line_indent(text, node.start)
        inner = indent + unit
        rendered = render(value, inner, unit, nl)
        return text[:node.start] + "[" + nl + inner + rendered + nl + indent + "]" + text[node.end:]
    sibling = items[index - 1] if index > 0 else items[0]
    multiline = is_multiline(text, node)
    item_indent = line_indent(text, items[0].start) if multiline else ""
    rendered = _render_like(text, sibling, value, item_indent)
    separator = ("," + nl + item_indent) if multiline else ", "
    if index < len(items):
        at = items[index].start
        return text[:at] + rendered + separator + text[at:]
    at = items[-1].end
    return text[:at] + separator + rendered + text[at:]


def set_member(text: str, pointer: str, key: str, value) -> str:
    root = parse(text)
    node = locate(root, pointer)
    if node.kind != "object":
        raise EditError(f"{pointer or '/'} 不是对象")
    unit, nl = indent_unit(text), newline_of(text)
    for name, member_start, child in node.members:
        if name == key:
            indent = line_indent(text, member_start)
            rendered = _render_like(text, child, value, indent)
            return text[:child.start] + rendered + text[child.end:]
    if not node.members:
        indent = line_indent(text, node.start)
        inner = indent + unit
        member = f"{_scalar(key)}: {render(value, inner, unit, nl)}"
        return text[:node.start] + "{" + nl + inner + member + nl + indent + "}" + text[node.end:]
    multiline = is_multiline(text, node)
    last_key, last_start, last = node.members[-1]
    indent = line_indent(text, last_start) if multiline else ""
    rendered = _render_like(text, last, value, indent)
    separator = ("," + nl + indent) if multiline else ", "
    return text[:last.end] + separator + f"{_scalar(key)}: {rendered}" + text[last.end:]


def remove_member(text: str, pointer: str, key: str) -> str:
    root = parse(text)
    node = locate(root, pointer)
    if node.kind != "object":
        raise EditError(f"{pointer or '/'} 不是对象")
    members = node.members
    for index, (name, member_start, child) in enumerate(members):
        if name != key:
            continue
        if len(members) == 1:
            return text[:node.start] + "{}" + text[node.end:]
        if index + 1 < len(members):
            return text[:member_start] + text[members[index + 1][1]:]
        previous = members[index - 1][2]
        return text[:previous.end] + text[child.end:]
    raise EditError(f"{pointer or '/'} 中没有 {key}")
