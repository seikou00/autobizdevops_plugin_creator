"""开发者可以手改的文字字段（D70）。

plugin.json、board_core/board_config.json、runtime/config/board.json 中，下面显式列出的文字字段（对话提示、展示文案）
允许开发者在生成后直接修改；文件的其余部分（命令、id、版本、节点清单等）仍然每次按核心配置重写。

build-manifest 为这三个文件另记：
- texts：每个文字字段这次生成的值的摘要。下次生成时，磁盘上的值与它不同，就是开发者改过的字段，保留开发者的值；
- structure：去掉文字字段（值换成空串）之后的摘要。check 靠它判断改动是否只在文字字段；
- customized：保留了开发者的值的字段及其摘要，没有时不记。

字段模式按 "." 分段：普通段是对象的键，"*" 匹配对象的任意键，"[]" 匹配数组的每一项、按该项的 id 命名，
例如 nodes.*.[].description 匹配到的字段名是 nodes.biz[draft].description。只有字符串值算文字字段。
"""

from __future__ import annotations

import copy

from scaffold.lib import fsio
from scaffold.lib.issues import Issue, error, warning

TEXT_FIELDS = {
    "plugin.json": ("description",),
    "board_core/board_config.json": (
        "inspectCommands.*.dialog_tips",
        "inspectCommands.*.system_prompt_inject",
    ),
    "runtime/config/board.json": (
        "template.label",
        "template.description",
        "stateLabels.*",
        "nodes.*.[].description",
        "nodes.*.[].nextAction.*.userMessage",
        "nodes.*.[].nextAction.*.dialogTips",
    ),
}
EDITABLE_HINT = {
    "plugin.json": "description",
    "board_core/board_config.json": "各平台的 dialog_tips、system_prompt_inject",
    "runtime/config/board.json": "template 的 label、description，stateLabels，节点的 description 和 nextAction 中的 userMessage、dialogTips",
}


def _walk(value, segments: list, prefix: str):
    head, rest = segments[0], segments[1:]
    if head == "[]":
        if not isinstance(value, list) or not rest:
            return
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                yield from _walk(item, rest, f"{prefix}[{item['id']}]")
        return
    if not isinstance(value, dict):
        return
    for key in (list(value) if head == "*" else [head] if head in value else []):
        name = f"{prefix}.{key}" if prefix else key
        if rest:
            yield from _walk(value[key], rest, name)
        elif isinstance(value[key], str):
            yield name, value, key


def slots(path: str, value) -> dict:
    """文字字段：字段名 → (所在对象, 键)，按模式顺序。"""
    result = {}
    for pattern in TEXT_FIELDS[path]:
        for name, parent, key in _walk(value, pattern.split("."), ""):
            result[name] = (parent, key)
    return result


def texts(path: str, value) -> dict:
    """文字字段：字段名 → 值。"""
    return {name: parent[key] for name, (parent, key) in slots(path, value).items()}


def structure(path: str, value) -> str:
    """去掉文字字段之后的摘要：文字字段的值换成空串，字段本身仍算结构。"""
    stripped = copy.deepcopy(value)
    for parent, key in slots(path, stripped).values():
        parent[key] = ""
    return fsio.digest(fsio.dump_json(stripped))


def problem_of(data: bytes) -> str | None:
    """手改后的文件至少要是 JSON 对象：宿主和运行框架都按对象读取。"""
    try:
        value = fsio.parse_json(data)
    except fsio.JsonError as exc:
        return f"不是合法的 JSON：{exc}"
    return None if isinstance(value, dict) else "顶层不是 JSON 对象"


def edited(path: str, value, record: dict) -> dict:
    """value 中被开发者改过的文字字段：与 record.texts 记录的生成值不同的字段 → 当前值。"""
    base = record.get("texts") or {}
    return {name: text for name, text in texts(path, value).items() if name in base and fsio.digest(text) != base[name]}


def merge(path: str, generated_data: bytes, disk: bytes | None, record: dict | None):
    """返回 (要写入的内容, build-manifest 的附加记录, issues)。

    在这次生成的内容上，把开发者改过的文字字段换回开发者的值；文字字段以外一律取生成结果。
    上次没有 texts 记录时（第一次生成、从旧版本升级）照常生成。"""
    generated = fsio.parse_json(generated_data)
    extra = {"structure": structure(path, generated),
             "texts": {name: fsio.digest(text) for name, text in sorted(texts(path, generated).items())}}
    issues: list[Issue] = []
    if disk is None or not (record or {}).get("texts"):
        return generated_data, extra, issues
    problem = problem_of(disk)
    if problem:
        issues.append(error("CUSTOMIZED_INVALID", f"{path} 手改过，但{problem}", file=path,
                            hint="修好这个文件；要恢复生成内容就删掉它再执行 autobiz-plugin doctor"))
        return generated_data, extra, issues
    current = fsio.parse_json(disk)
    if record.get("structure") and structure(path, current) != record["structure"]:
        issues.append(warning("DRIFT_GENERATED", f"{path} 中可改文字以外的改动已按核心配置重写", file=path,
                              hint=f"这个文件只能改：{EDITABLE_HINT[path]}"))
    changes = edited(path, current, record)
    merged = copy.deepcopy(generated)
    kept, stale = {}, []
    for name, (parent, key) in slots(path, merged).items():
        if name not in changes or changes[name] == parent[key]:
            continue
        if fsio.digest(parent[key]) != record["texts"][name]:
            stale.append(name)                      # 开发者改过，这次生成的值也变了：保留开发者的值
        parent[key] = changes[name]
        kept[name] = fsio.digest(changes[name])
    if stale:
        issues.append(warning("CUSTOMIZED_STALE", f"{path} 中以下文字保留了你改过的版本，但核心配置的变化也改到了它们："
                              + "、".join(stale), file=path,
                              hint="确认手改的文字仍然适用；要改用生成的文字，删掉文件再执行 autobiz-plugin doctor"
                                   "（这个文件中的手改会全部恢复为生成内容）"))
    if not kept:
        return generated_data, extra, issues
    extra["customized"] = dict(sorted(kept.items()))
    return fsio.dump_json(merged), extra, issues
