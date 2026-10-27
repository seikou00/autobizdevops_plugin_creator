#!/usr/bin/env python3
"""检查 input-config.md 中的默认值与 Schema 的 default 是否一致（D27：默认值只有一个来源）。

只看“默认值”表（表头第二列为“默认”或“默认值”），每张表按所在章节对应到一个 Schema 位置（SECTIONS）：

1. 表中写成代码的字面量默认值必须等于 Schema 的 default；对象类字段比较补全后的结果（例如 stateLabels）；
2. Schema 写了 default 而表中写的不是代码，或者表中写了 JSON 字面量而 Schema 没有 default，都算不一致；
3. 章节对应的 Schema 范围内，每个带 default 的字段都要在表中出现（自己或上级字段占一行）。

推导出来的默认值（例如 `plugin.name`）不是 JSON 字面量，Schema 也没有 default，不检查。

用法：python3 tests/check_schema_defaults.py [--schemas DIR] [文档 ...]
退出码：0 一致；1 有不一致；2 用法错误或文件无法读取。
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = [REPO / "docs" / "input-config.md",
                REPO / "demo" / "autobiz-plugin-creator-demo" / "skills" / "autobiz-plugin-creator" / "references"
                / "input-config.md"]
# 章节编号 → (Schema 文件, Schema 内的起点)。起点是 #/definitions/<名> 或用 . 连接的属性路径，空串为根
SECTIONS = {
    "2.9": ("workflow.schema.json", "#/definitions/gitOutput"),
    "3.4": ("plugin-scaffold.schema.json", "runtime"),
    "4.1.1": ("modules/board.schema.json", "target"),
    "4.1.2": ("modules/board.schema.json", "display"),
    "4.1.3": ("modules/board.schema.json", "capabilities.knowledgeSedimentation"),
    "4.2": ("modules/session.schema.json", ""),
    "4.3": ("modules/knowledge.schema.json", ""),
    "4.5": ("modules/artifactSync.schema.json", ""),
}
HEADING = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\s")
CODE = re.compile(r"`([^`]*)`")
MISSING = object()


def resolve(schema, root):
    while "$ref" in schema:
        schema = root["definitions"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def properties(schema, root):
    """本层与 allOf 中声明的属性。"""
    schema = resolve(schema, root)
    result = {}
    for option in schema.get("allOf", []):
        result.update(properties(option, root))
    result.update(schema.get("properties", {}))
    return result


def default_of(schema, root):
    return schema.get("default", resolve(schema, root).get("default", MISSING))


def fill(value, schema, root):
    if isinstance(value, dict):
        for key, item in properties(schema, root).items():
            if key not in value and default_of(item, root) is not MISSING:
                value[key] = copy.deepcopy(default_of(item, root))
            if key in value:
                fill(value[key], item, root)
    return value


def effective_default(schema, root):
    """字段的默认值；对象补全子字段后再比较，例如 stateLabels 的 {} 补全为五个标签。"""
    default = default_of(schema, root)
    if default is MISSING:
        return MISSING
    return fill(copy.deepcopy(default), schema, root)


def section_schema(root, start):
    if start.startswith("#/"):
        return resolve({"$ref": start}, root)
    return locate(root, root, start) if start else root


def locate(schema, root, field):
    for name in field.split("."):
        schema = properties(schema, root).get(name)
        if schema is None:
            return None
    return schema


def is_container(schema, root):
    return bool(properties(schema, root))


def leaf_defaults(schema, root, prefix=""):
    """起点之下带 default 的非对象字段：不进入 additionalProperties 的取值。"""
    for name, item in properties(schema, root).items():
        path = f"{prefix}{name}"
        if is_container(item, root):
            yield from leaf_defaults(item, root, path + ".")
        elif default_of(item, root) is not MISSING:
            yield path


def literal_matches(code, value):
    try:
        parsed = json.loads(code)
    except ValueError:
        return isinstance(value, str) and code == value
    return type(parsed) is type(value) and parsed == value


def is_json_literal(code):
    try:
        json.loads(code)
    except ValueError:
        return False
    return True


def default_tables(text):
    """返回 [(章节编号, 行号, 字段单元格, 默认值单元格)]。"""
    rows, section, in_table = [], None, False
    lines = text.split("\n")
    for number, line in enumerate(lines, 1):
        heading = HEADING.match(line)
        if heading:
            section, in_table = heading.group(1), False
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in line.replace("\\|", "\0").strip("|").split("|")]
        cells = [cell.replace("\0", "|") for cell in cells]
        if not in_table:
            in_table = len(cells) >= 2 and cells[0] == "字段" and cells[1] in ("默认", "默认值")
            continue
        if set(cells[0]) <= set("-: "):
            continue
        rows.append((section, number, cells[0], cells[1]))
    return rows


def check(doc, schemas):
    problems = []
    rows = default_tables(doc.read_text(encoding="utf-8"))
    covered = {}
    for section, line, field_cell, default_cell in rows:
        where = f"{doc.name}:{line}"
        if section not in SECTIONS:
            problems.append(f"{where} §{section} 有默认值表，但 SECTIONS 中没有对应的 Schema 位置")
            continue
        file, start = SECTIONS[section]
        root = schemas[file]
        names = CODE.findall(field_cell)
        if not names or any("<" in name for name in names):
            continue
        codes = CODE.findall(default_cell)
        covered.setdefault(section, set()).update(names)
        for index, name in enumerate(names):
            schema = locate(section_schema(root, start), root, name)
            if schema is None:
                problems.append(f"{where} 字段 {name} 在 {file} 中不存在")
                continue
            expected = effective_default(schema, root)
            code = codes[index] if len(codes) == len(names) else (codes[0] if len(names) == 1 and codes else None)
            if expected is MISSING:
                if code is not None and is_json_literal(code):
                    problems.append(f"{where} 字段 {name} 写了默认值 {code}，但 {file} 中没有 default")
            elif code is None:
                problems.append(f"{where} 字段 {name} 的默认值应写成代码，与 {file} 一致："
                                f"{json.dumps(expected, ensure_ascii=False)}")
            elif not literal_matches(code, expected):
                problems.append(f"{where} 字段 {name} 的默认值是 {code}，{file} 中是 "
                                f"{json.dumps(expected, ensure_ascii=False)}")
    for section, (file, start) in SECTIONS.items():
        root = schemas[file]
        base = section_schema(root, start)
        names = covered.get(section, set())
        for path in leaf_defaults(base, root):
            if not any(path == name or path.startswith(name + ".") for name in names):
                problems.append(f"{doc.name} §{section} 缺少 {path}：{file} 中它的默认值是 "
                                f"{json.dumps(effective_default(locate(base, root, path), root), ensure_ascii=False)}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查文档默认值与 Schema 是否一致")
    parser.add_argument("docs", nargs="*", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--schemas", type=Path, default=REPO / "schemas")
    args = parser.parse_args(argv)
    try:
        schemas = {file: json.loads((args.schemas / file).read_text(encoding="utf-8"))
                   for file in {file for file, _ in SECTIONS.values()}}
    except (OSError, ValueError) as error:
        print(f"无法读取 Schema：{error}", file=sys.stderr)
        return 2
    problems = []
    for doc in args.docs:
        if not doc.is_file():
            print(f"找不到文档：{doc}", file=sys.stderr)
            return 2
        problems += check(doc, schemas)
    for problem in problems:
        print(problem)
    print(f"结果：{len(problems)} 处不一致" if problems else "结果：文档默认值与 Schema 一致")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
