"""宿主命令输出的结构校验（schemas/host/outputs.schema.json，Q11.3）。"""

from __future__ import annotations

from scaffold.lib import jsonschema

SCHEMA = "host/outputs.schema.json"


def check_shape(key: str, payload) -> list:
    """返回 [(JSON Pointer, 原因)]；key 为命令键，片段命令用 update_state。"""
    root = jsonschema.load_schema(SCHEMA)
    name = "update_state" if key == "model:update_state" else key
    if name not in root["definitions"]:
        return []
    if isinstance(payload, dict) and payload.get("ok") is False:
        return jsonschema.validate(payload, {"$ref": "#/definitions/failure"}, root=root)
    return jsonschema.validate(payload, {"$ref": f"#/definitions/{name}"}, root=root)
