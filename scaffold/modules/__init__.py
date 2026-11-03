"""模块契约：发现、实例化与上下文（interfaces.md §2，scaffold.md 单元 6）。"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from scaffold import CORE_VERSION, resources
from scaffold.build.load import MODULE_KEYS

PACKAGE_DIRS = {"board": "board", "session": "session", "knowledge": "knowledge", "artifactSync": "artifact_sync"}


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    version: str
    title: str
    description: str
    schema: str
    entry: str
    core: bool
    package: str                    # 模块包相对 scaffold/ 的目录，例如 modules/knowledge


@dataclass(frozen=True)
class ModuleContext:
    root: Path                      # 插件目录，只读
    tree: object                    # 插件目录的只读视图（含内存中的修改）
    package: str                    # 模块包，资源路径前缀 scaffold/modules/<dir>
    core_version: str
    enabled: frozenset

    def package_file(self, rel: str) -> bytes:
        return resources.read_bytes(f"{self.package}/{rel}")


class Module:
    """模块的基类：validate 只读、无副作用；contribute 是纯函数（漂移检测依赖这一点）。"""

    spec: ModuleSpec

    def __init__(self, spec: ModuleSpec):
        self.spec = spec

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def version(self) -> str:
        return self.spec.version

    def validate(self, ir, options: dict, ctx: ModuleContext) -> list:
        return []

    def contribute(self, ir, options: dict, ctx: ModuleContext):
        raise NotImplementedError


@lru_cache(maxsize=None)
def discover() -> dict:
    specs = {}
    for module_id in MODULE_KEYS:
        package = f"scaffold/modules/{PACKAGE_DIRS[module_id]}"
        data = json.loads(resources.read_text(f"{package}/module.json"))
        core = bool(data.get("core", False))
        specs[module_id] = ModuleSpec(id=data["id"], version=CORE_VERSION if core else data["version"],
                                      title=data.get("title", ""), description=data.get("description", ""),
                                      schema=data["schema"], entry=data["entry"], core=core, package=package)
    return specs


def instantiate(spec: ModuleSpec) -> Module:
    module_name, class_name = spec.entry.split(":", 1)
    package = "scaffold." + spec.package[len("scaffold/"):].replace("/", ".")
    module = importlib.import_module(f"{package}.{module_name}")
    return getattr(module, class_name)(spec)


def enabled_modules(normalized) -> dict:
    specs = discover()
    return {module_id: instantiate(specs[module_id]) for module_id in MODULE_KEYS if module_id in normalized.modules}


def context(normalized, module: Module) -> ModuleContext:
    return ModuleContext(root=normalized.inputs.root, tree=normalized.inputs.tree, package=module.spec.package,
                         core_version=CORE_VERSION, enabled=frozenset(normalized.enabled))
