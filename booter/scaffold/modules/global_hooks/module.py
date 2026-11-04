"""插件全局钩子模块（D62）：按 modules/globalHooks.json 的 hooks 启用 hooks/ 下的公共钩子。

每个钩子的脚本拷到插件根目录的 hooks/<id>/（module），条目通过 Contribution.hooks 合并进 hooks/hooks.json：
排在框架的产物检查钩子之后、开发者 plugin.hooks 的条目之前，按 hooks 中列出的顺序（interfaces.md §4.8）。
"""

from __future__ import annotations

from scaffold.build.contribute import Contribution, FileSpec
from scaffold.lib.issues import error
from scaffold.modules import Module
from scaffold.modules.global_hooks.catalog import catalog

FILE = "modules/globalHooks.json"


class GlobalHooksModule(Module):
    def validate(self, ir, options, ctx):
        available = catalog()
        issues, seen = [], set()
        for index, hook_id in enumerate(options.get("hooks", [])):
            pointer = f"/hooks/{index}"
            if hook_id in seen:
                issues.append(error("GLOBAL_HOOK_DUP", f"全局钩子 {hook_id} 重复", file=FILE, pointer=pointer,
                                    hint="删掉重复的一项"))
            elif hook_id not in available:
                issues.append(error("GLOBAL_HOOK_UNKNOWN", f"没有全局钩子 {hook_id}", file=FILE, pointer=pointer,
                                    hint="可用：" + "、".join(available) + "（autobiz-plugin hook list）"))
            seen.add(hook_id)
        return issues

    def contribute(self, ir, options, ctx):
        available = catalog()
        files, hooks = [], {}
        for hook_id in dict.fromkeys(options.get("hooks", [])):
            spec = available[hook_id]
            files += [FileSpec(f"{spec.target}/{name}", "module", content=spec.file_bytes(name)) for name in spec.files]
            for event, items in spec.rendered_entries().items():
                hooks.setdefault(event, []).extend(items)
        return Contribution(files=files, hooks=hooks)
