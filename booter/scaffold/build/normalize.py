"""按 Schema 的 default 补全核心配置，去掉 $schema；不做推导（D27、D46）。"""

from __future__ import annotations

from dataclasses import dataclass

from scaffold.build.load import MODULE_KEYS, SCHEMAS, Inputs
from scaffold.lib import jsonschema

CORE_MODULES = ("board", "session")


@dataclass(frozen=True)
class Normalized:
    inputs: Inputs
    entry: dict
    workflow: dict
    modules: dict           # 启用的模块 → 补全后的配置；board、session 未引用时为全部默认值

    @property
    def enabled(self) -> tuple[str, ...]:
        return tuple(key for key in MODULE_KEYS if key in self.modules)


def _complete(value: dict, schema_name: str) -> dict:
    schema = jsonschema.load_schema(schema_name)
    result = jsonschema.apply_defaults(value, schema)
    result.pop("$schema", None)
    return result


def normalize(inputs: Inputs) -> Normalized:
    entry = _complete(inputs.entry, SCHEMAS["entry"])
    workflow = _complete(inputs.workflow, SCHEMAS["workflow"])
    modules = {}
    for key in MODULE_KEYS:
        if key in inputs.modules:
            modules[key] = _complete(inputs.modules[key], SCHEMAS[key])
        elif key in CORE_MODULES:
            modules[key] = _complete({}, SCHEMAS[key])
    return Normalized(inputs, entry, workflow, modules)
