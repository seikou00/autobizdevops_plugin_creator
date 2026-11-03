"""当前脚手架与 build-manifest 记录的版本比较（scaffold.md 单元 13，Q13.2，D57）。

| 情况 | 处理 |
|---|---|
| 版本相同 | 照常 |
| 版本高于记录，coreVersion 主版本不变 | lint、check 报 warning SCAFFOLD_VERSION_CHANGED；doctor 替换 managed、module 文件 |
| coreVersion 主版本变化 | error CORE_MAJOR_CHANGED，doctor --allow-major-upgrade 放行 |
| 任一版本低于记录 | error SCAFFOLD_OUTDATED：doctor 会把运行框架降级，拒绝执行，没有放行参数 |
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scaffold import CORE_VERSION, SCAFFOLD_VERSION
from scaffold.lib.issues import error, warning

MANIFEST = "runtime/build-manifest.json"


def parse(version: str) -> tuple:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


@dataclass
class VersionChanges:
    scaffold: tuple | None = None           # (记录的版本, 当前版本)
    core: tuple | None = None
    modules: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        def pair(value):
            return None if value is None else {"from": value[0], "to": value[1]}

        return {"scaffold": pair(self.scaffold), "core": pair(self.core),
                "modules": {key: pair(value) for key, value in self.modules.items()}}

    @property
    def changed(self) -> bool:
        return bool(self.scaffold or self.core or self.modules)


def compare_versions(previous: dict | None, modules: dict, *, allow: frozenset = frozenset(),
                     report_upgrade: bool = True):
    """返回 (VersionChanges, issues)。modules 为启用的模块（id → Module）；previous 为 None 时不比较。"""
    changes = VersionChanges()
    issues = []
    if previous is None:
        return changes, issues
    pairs = [("scaffold", "脚手架", previous.get("scaffoldVersion"), SCAFFOLD_VERSION),
             ("core", "运行框架", previous.get("coreVersion"), CORE_VERSION)]
    recorded_modules = previous.get("modules", {})
    pairs += [(f"module:{module_id}", f"模块 {module_id}", recorded_modules[module_id], module.version)
              for module_id, module in modules.items() if module_id in recorded_modules]
    older, newer = [], []
    for key, label, recorded, current in pairs:
        if recorded is None or recorded == current:
            continue
        if key == "scaffold":
            changes.scaffold = (recorded, current)
        elif key == "core":
            changes.core = (recorded, current)
        else:
            changes.modules[key.split(":", 1)[1]] = (recorded, current)
        (older if parse(current) < parse(recorded) else newer).append(f"{label} {recorded} → {current}")
    if older:
        issues.append(error("SCAFFOLD_OUTDATED", "当前脚手架比生成这个插件时用的旧：" + "、".join(older), file=MANIFEST,
                            hint="先更新 autobiz-plugin.pyz 再执行 doctor，否则会把插件降级"))
        return changes, issues
    if changes.core and parse(changes.core[0])[0] != parse(changes.core[1])[0]:
        if "major-upgrade" in allow:
            issues.append(warning("CORE_MAJOR_CHANGED", f"运行框架跨主版本升级 {changes.core[0]} → {changes.core[1]}，"
                                  "已有项目的状态是否兼容请看版本说明", file=MANIFEST))
        else:
            issues.append(error("CORE_MAJOR_CHANGED", f"运行框架主版本从 {changes.core[0]} 变为 {changes.core[1]}",
                                file=MANIFEST, hint="确认要跨主版本升级时执行 autobiz-plugin doctor --allow-major-upgrade"))
        return changes, issues
    if newer and report_upgrade:
        issues.append(warning("SCAFFOLD_VERSION_CHANGED", "脚手架已更新：" + "、".join(newer), file=MANIFEST,
                              hint="执行 autobiz-plugin doctor 替换托管文件"))
    return changes, issues


def entry_outdated(entry) -> list:
    """入口文件的 scaffoldVersion（格式主版本）比脚手架支持的高时报 SCAFFOLD_OUTDATED，而不是 INPUT_SCHEMA。"""
    value = entry.get("scaffoldVersion") if isinstance(entry, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 1:
        return [error("SCAFFOLD_OUTDATED", f"入口文件的 scaffoldVersion 是 {value}，当前脚手架只支持 1",
                      file="plugin.scaffold.json", pointer="/scaffoldVersion", hint="更新 autobiz-plugin.pyz")]
    return []
