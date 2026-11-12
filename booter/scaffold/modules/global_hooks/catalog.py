"""全局钩子目录（D62）：hooks/<包>/ 下一个 hook.json 加上 files/ 中的脚本就是一个可选钩子。

开发者在 modules/globalHooks.json 的 hooks 中按 id 列出要启用的钩子；globalHooks 模块把脚本拷到插件的
hooks/<id>/，把 hook.json 的 entries 合并进 hooks/hooks.json。新增钩子只需在 hooks/ 下
加一个目录，不用改代码。

hook.json 字段：id（kebab-case，全局唯一）、title、description、files（files/ 下要拷贝的文件）、
entries（事件名 → 条目数组，写法与 hooks.json 相同，command 中的 ${hookDir} 在 build 时替换为 hooks/<id>）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from scaffold import resources

CATALOG = "scaffold/modules/global_hooks/hooks"
HOOK_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HOOK_DIR = "${hookDir}"


@dataclass(frozen=True)
class HookSpec:
    id: str
    title: str
    description: str
    package: str                    # 相对脚手架资源根的目录，例如 scaffold/modules/global_hooks/hooks/secrets_check
    files: tuple
    entries: dict

    def file_bytes(self, name: str) -> bytes:
        return resources.read_bytes(f"{self.package}/files/{name}")

    @property
    def target(self) -> str:
        """脚本在插件中的目录。"""
        return f"hooks/{self.id}"

    def rendered_entries(self) -> dict:
        text = json.dumps(self.entries, ensure_ascii=False).replace(HOOK_DIR, self.target)
        return json.loads(text)


@lru_cache(maxsize=None)
def catalog() -> dict:
    """id → HookSpec，按 id 排序。目录结构或 hook.json 不对时直接抛错：这是脚手架自身的缺陷，由测试拦住。"""
    specs = {}
    for rel in resources.list_files(CATALOG):
        parts = rel.split("/")
        if len(parts) != 2 or parts[1] != "hook.json":
            continue
        package = f"{CATALOG}/{parts[0]}"
        data = json.loads(resources.read_text(f"{package}/hook.json"))
        spec = HookSpec(id=data["id"], title=data["title"], description=data["description"], package=package,
                        files=tuple(data.get("files", [])), entries=data["entries"])
        if not HOOK_ID.match(spec.id) or spec.id in specs:
            raise ValueError(f"全局钩子 id 不合法或重复：{spec.id}（{package}/hook.json）")
        for name in spec.files:
            if not resources.exists(f"{package}/files/{name}"):
                raise ValueError(f"全局钩子 {spec.id} 缺少文件 files/{name}")
        specs[spec.id] = spec
    return {hook_id: specs[hook_id] for hook_id in sorted(specs)}
