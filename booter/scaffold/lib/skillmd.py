"""技能目录查找与 SKILL.md 的读写（scaffold.md 单元 2，output-spec.md §6.1，D45）。

frontmatter 只支持两种写法：单行 `键: 值`（值可以加引号），以及 `metadata:` 下一层缩进的单行 `键: 值`。
状态维护片段沿用文件原有的换行方式（D42）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scaffold.lib import fsio

STATE_BEGIN = "<!-- plugin workflow: begin state -->"
STATE_END = "<!-- plugin workflow: end state -->"
LEGACY_STATE = re.compile(r"<!--\s*scaffold:begin state\s*-->.*?<!--\s*scaffold:end state\s*-->", re.S)
LEGACY_ARTIFACTS = re.compile(r"<!--\s*scaffold:begin artifacts\s*-->.*?<!--\s*scaffold:end artifacts\s*-->(\r?\n){0,2}",
                              re.S)
TODO_DESCRIPTION = "[TODO: 做什么；在什么情况下使用]"
ALLOWED_KEYS = ("name", "description", "license", "allowed-tools", "metadata")
UPDATE_STATE = 'python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint'
_TOP = re.compile(r"^([A-Za-z0-9_-]+):(?:[ \t]+(.*?))?[ \t]*$")


@dataclass(frozen=True)
class Frontmatter:
    fields: dict
    body_start: int                 # 正文起始偏移；没有 frontmatter 时为 0
    errors: list = field(default_factory=list)
    present: bool = False
    lines: tuple = ()               # frontmatter 内的原始行（不含首尾 ---），供迁移使用


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def read_text(data: bytes) -> str:
    return fsio.decode(data)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    return value


def parse_frontmatter(text: str) -> Frontmatter:
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return Frontmatter({}, 0)
    end = None
    offset = len(lines[0])
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            end = index
            break
    if end is None:
        return Frontmatter({}, 0, ["frontmatter 缺少结束的 ---"], present=True)
    body_start = offset + sum(len(line) for line in lines[1:end + 1])
    fields: dict = {}
    errors: list = []
    block = None
    for number, raw in enumerate(lines[1:end], 2):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            stripped = line.strip()
            match = _TOP.match(stripped)
            if block is None:
                errors.append(f"第 {number} 行：只支持 metadata 下一层缩进的 `键: 值`")
            elif stripped.startswith("- ") or stripped == "-":
                errors.append(f"第 {number} 行：不支持列表，请改写成单行 `键: 值`")
            elif not match or match.group(2) is None:
                errors.append(f"第 {number} 行：metadata 下只支持一层单行 `键: 值`")
            elif len(line) - len(line.lstrip()) != block[1]:
                errors.append(f"第 {number} 行：metadata 下只支持一层缩进")
            else:
                fields[block[0]][match.group(1)] = _unquote(match.group(2))
            continue
        block = None
        match = _TOP.match(line)
        if not match:
            errors.append(f"第 {number} 行：无法解析，请改写成单行 `键: 值`")
            continue
        key, value = match.group(1), match.group(2)
        if value is None:
            if key == "metadata":
                fields[key] = {}
                following = next((item for item in lines[number:end] if item.strip()), "")
                indent = len(following) - len(following.lstrip(" \t"))
                block = (key, indent or 2)
            else:
                errors.append(f"第 {number} 行：{key} 的值不能为空或换行书写，请改写成单行 `键: 值`")
            continue
        if value[:1] in (">", "|"):
            errors.append(f"第 {number} 行：不支持块标量 {value[:1]}，请把 {key} 改写成单行")
            continue
        fields[key] = _unquote(value)
    return Frontmatter(fields, body_start, errors, True, tuple(line.rstrip("\r\n") for line in lines[1:end]))


def description_of(text: str):
    value = parse_frontmatter(text).fields.get("description")
    return value if isinstance(value, str) else None


def is_placeholder(description) -> bool:
    return not description or description.strip().startswith("[TODO")


def find_skill_dir(tree, skill: str):
    """在 skills/<skill>/ 和 skills/*/<skill>/ 找含 SKILL.md 的目录（input-config.md §5）。

    返回 (唯一命中的目录或 None, 全部候选)；目录为相对插件根的 POSIX 路径。
    """
    candidates = []
    if tree.is_file(f"skills/{skill}/SKILL.md"):
        candidates.append(f"skills/{skill}")
    for group in tree.list_dir("skills"):
        if group == skill or not tree.is_dir(f"skills/{group}"):
            continue
        if tree.is_file(f"skills/{group}/{skill}/SKILL.md"):
            candidates.append(f"skills/{group}/{skill}")
    return (candidates[0] if len(candidates) == 1 else None), candidates


def render_state_block(node_id: str, terminal: bool) -> str:
    lines = [STATE_BEGIN, "## 技能状态维护", ""]
    if terminal:
        lines.append(f"技能完成执行：{UPDATE_STATE} archived")
    else:
        lines.append(f"技能开始执行：{UPDATE_STATE} {node_id}_in_progress")
        lines.append("")
        lines.append(f"技能完成执行：{UPDATE_STATE} {node_id}_done")
    lines.append(STATE_END)
    return "\n".join(lines)


def blank_skill(skill: str, block: str) -> str:
    return f"---\nname: {skill}\ndescription: {TODO_DESCRIPTION}\n---\n\n{block}\n"


def _span(text: str):
    begin = text.find(STATE_BEGIN)
    if begin < 0:
        return None
    end = text.find(STATE_END, begin)
    if end < 0:
        return None
    return begin, end + len(STATE_END)


def has_state(text: str) -> bool:
    return _span(text) is not None


def state_inner(text: str):
    span = _span(text)
    if span is None:
        return None
    inner = text[span[0] + len(STATE_BEGIN):span[1] - len(STATE_END)]
    return inner.replace("\r\n", "\n").strip("\n")


def state_digest(text: str):
    inner = state_inner(text)
    return None if inner is None else fsio.digest(inner)


def block_digest(block: str) -> str:
    return state_digest(block)


def upsert_state(text: str, block: str) -> str:
    nl = newline_of(text)
    block = block.replace("\n", nl)
    span = _span(text)
    if span is not None:
        return text[:span[0]] + block + text[span[1]:]
    text = LEGACY_ARTIFACTS.sub("", text)
    legacy = LEGACY_STATE.search(text)
    if legacy:
        return text[:legacy.start()] + block + text[legacy.end():]
    front = parse_frontmatter(text)
    head, rest = text[:front.body_start], text[front.body_start:]
    rest = rest.lstrip("\r\n")
    if front.present and front.body_start:
        return head + nl + block + nl + (nl + rest if rest else "")
    return block + nl + (nl + rest if rest else "")


def remove_state(text: str) -> str:
    span = _span(text)
    if span is None:
        return text
    start, end = span
    nl = newline_of(text)
    for _ in range(2):
        if text.startswith(nl, end):
            end += len(nl)
    return text[:start] + text[end:]


def set_name(text: str, skill: str) -> tuple[str, bool]:
    """把 frontmatter 的 name 改为 skill；没有 frontmatter 时补上。返回 (新文本, 是否改动)。"""
    nl = newline_of(text)
    front = parse_frontmatter(text)
    if not front.present:
        return f"---{nl}name: {skill}{nl}description: {TODO_DESCRIPTION}{nl}---{nl}{nl}" + text, True
    if front.fields.get("name") == skill:
        return text, False
    head = text[:front.body_start]
    lines = head.split(nl)
    for index, line in enumerate(lines[1:], 1):
        if re.match(r"^name:", line):
            lines[index] = f"name: {skill}"
            break
    else:
        lines.insert(1, f"name: {skill}")
    return nl.join(lines) + text[front.body_start:], True


def migrate_frontmatter(text: str) -> tuple[str, list[str]]:
    """顶层的 version、author 移到 metadata 下（D8），add skill 导入时使用。"""
    front = parse_frontmatter(text)
    if not front.present or front.errors:
        return text, []
    moved = [line for line in front.lines if re.match(r"^(version|author):", line)]
    if not moved:
        return text, []
    nl = newline_of(text)
    kept = [line for line in front.lines if line not in moved]
    metadata = [f"  {line}" for line in moved]
    if any(line == "metadata:" for line in kept):
        index = kept.index("metadata:") + 1
        while index < len(kept) and kept[index][:1] in (" ", "\t"):
            index += 1
        kept[index:index] = metadata
    else:
        kept += ["metadata:"] + metadata
    notes = [f"frontmatter 顶层的 {line.split(':', 1)[0]} 已移到 metadata 下" for line in moved]
    return f"---{nl}" + nl.join(kept) + f"{nl}---{nl}" + text[front.body_start:], notes
