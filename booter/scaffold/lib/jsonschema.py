"""draft-07 子集：只实现 D43 列出的 18 个关键字。

validate 返回 [(JSON Pointer, 原因)]；apply_defaults 按 Schema 的 default 补全（D27）：
对象要有 default: {} 才会在缺省时创建，oneOf 只进入匹配的那一种写法。
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache

from scaffold import resources

KEYWORDS = frozenset({"$ref", "additionalProperties", "const", "default", "enum", "items", "maxLength", "minItems",
                      "minLength", "minProperties", "minimum", "not", "oneOf", "pattern", "properties",
                      "propertyNames", "required", "type"})
ANNOTATIONS = frozenset({"$schema", "$id", "title", "description", "definitions"})
TYPE_NAMES = {"object": "对象", "array": "数组", "string": "字符串", "integer": "整数", "number": "数字",
              "boolean": "布尔值", "null": "null"}


@lru_cache(maxsize=None)
def _load(name: str) -> str:
    return resources.read_text(f"schemas/{name}")


def load_schema(name: str) -> dict:
    """从 schemas/ 读取，例如 "modules/board.schema.json"。每次返回新的副本。"""
    return json.loads(_load(name))


def escape(token) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def resolve(schema: dict, root: dict) -> dict:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            raise ValueError(f"只支持本文件内的 $ref: {ref}")
        schema = root["definitions"][ref[len("#/definitions/"):]]
        seen += 1
        if seen > 32:
            raise ValueError(f"$ref 循环: {ref}")
    return schema


def _type_matches(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise ValueError(f"未知类型: {name}")


def _show(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def validate(instance, schema: dict, *, root: dict | None = None, pointer: str = "") -> list[tuple[str, str]]:
    root = schema if root is None else root
    errors: list[tuple[str, str]] = []
    _validate(instance, schema, root, pointer, errors)
    return errors


def _validate(value, schema, root, pointer, errors):
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append((pointer, "不允许出现"))
        return
    if "$ref" in schema:
        _validate(value, resolve({"$ref": schema["$ref"]}, root), root, pointer, errors)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_matches(value, name) for name in names):
            expected = "或".join(TYPE_NAMES.get(name, name) for name in names)
            errors.append((pointer, f"应为{expected}"))
            return
    if "const" in schema and value != schema["const"]:
        errors.append((pointer, f"只能是 {_show(schema['const'])}"))
    if "enum" in schema and value not in schema["enum"]:
        errors.append((pointer, "只能是 " + "、".join(_show(item) for item in schema["enum"]) + " 之一"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append((pointer, "不能为空" if schema["minLength"] == 1 else f"至少 {schema['minLength']} 个字符"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append((pointer, f"不能超过 {schema['maxLength']} 个字符"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append((pointer, f"格式不正确：{_show(value)}"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((pointer, f"不能小于 {schema['minimum']}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append((pointer, f"至少要有 {schema['minItems']} 项"))
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], root, f"{pointer}/{index}", errors)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append((pointer, f"缺少必填字段 {key}"))
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append((pointer, f"至少要有 {schema['minProperties']} 个字段"))
        for key, item in value.items():
            child = f"{pointer}/{escape(key)}"
            if "propertyNames" in schema:
                for _, reason in validate(key, schema["propertyNames"], root=root, pointer=child):
                    errors.append((child, f"键 {_show(key)} {reason}"))
            if key in properties:
                _validate(item, properties[key], root, child, errors)
            elif "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    allowed = "、".join(properties) if properties else "无"
                    errors.append((child, f"不认识的字段 {key}（可用字段：{allowed}）"))
                elif isinstance(extra, dict):
                    _validate(item, extra, root, child, errors)
    if "not" in schema and not validate(value, schema["not"], root=root, pointer=pointer):
        excluded = schema["not"]
        if isinstance(excluded, dict) and set(excluded) == {"required"}:
            errors.append((pointer, "不能写 " + "、".join(excluded["required"])))
        else:
            errors.append((pointer, "不能是被排除的写法"))
    if "oneOf" in schema:
        results = [validate(value, option, root=root, pointer=pointer) for option in schema["oneOf"]]
        matched = [index for index, result in enumerate(results) if not result]
        if not matched:
            errors.extend(min(results, key=len))
        elif len(matched) > 1:
            errors.append((pointer, "同时符合多种写法，无法确定"))


def default_of(schema: dict, root: dict):
    if "default" in schema:
        return True, schema["default"]
    target = resolve(schema, root)
    if isinstance(target, dict) and "default" in target:
        return True, target["default"]
    return False, None


def apply_defaults(instance, schema: dict, *, root: dict | None = None):
    root = schema if root is None else root
    return _fill(copy.deepcopy(instance), schema, root)


def _fill(value, schema, root):
    schema = resolve(schema, root)
    if not isinstance(schema, dict):
        return value
    if "oneOf" in schema:
        for option in schema["oneOf"]:
            if not validate(value, option, root=root):
                value = _fill(value, option, root)
                break
    if isinstance(value, dict):
        for key, child in schema.get("properties", {}).items():
            if key not in value:
                present, default = default_of(child, root)
                if not present:
                    continue
                value[key] = copy.deepcopy(default)
            value[key] = _fill(value[key], child, root)
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        value[:] = [_fill(item, schema["items"], root) for item in value]
    return value


def keywords_used(schema, found=None) -> set:
    """Schema 中出现的关键字（测试用：只能使用 KEYWORDS 与说明性的键）。"""
    found = set() if found is None else found
    if isinstance(schema, dict):
        for key, value in schema.items():
            found.add(key)
            if key in ("properties", "definitions"):
                for item in value.values():
                    keywords_used(item, found)
            elif key in ("items", "additionalProperties", "not", "propertyNames") and isinstance(value, dict):
                keywords_used(value, found)
            elif key == "oneOf":
                for item in value:
                    keywords_used(item, found)
    return found
