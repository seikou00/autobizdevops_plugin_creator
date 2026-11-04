"""模块贡献的类型与合并规则（interfaces.md §2.2、§2.3，D50）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from scaffold.lib.issues import Issue, error

MERGE_ORDER = ("framework", "board", "session", "knowledge", "artifactSync", "globalHooks")
CORE_ENTRY_KEYS = ("apiVersion", "modules", "boardEvents")


@dataclass(frozen=True)
class FileSpec:
    dst: str                                  # 插件内相对路径
    ownership: str                            # "managed" | "module" | "generated" | "seeded"
    src: Optional[str] = None                 # "files/…" 相对模块包；"runtime/…"、"schemas/…" 相对仓库根目录
    content: Optional[Union[str, bytes]] = None
    replaceable: bool = False                 # 插件可以整个替换：与记录不符时保留插件的版本，不报漂移


@dataclass(frozen=True)
class CommandSpec:
    script: Optional[str] = None              # 相对插件根；展开为 {py} "${pluginPath}/<script>" <args>
    args: str = ""                            # 可含 {platform}
    value: Optional[str] = None               # 非命令值，例如 knowledge_path


@dataclass
class Contribution:
    files: list = field(default_factory=list)
    entries: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    runtime_config: dict = field(default_factory=dict)
    inspect_commands: dict = field(default_factory=dict)
    knowledge_assembly: Optional[dict] = None
    skills: list = field(default_factory=list)
    hooks: dict = field(default_factory=dict)             # 宿主钩子：事件名 → 条目数组，合并进 hooks/hooks.json


@dataclass
class Merged:
    files: dict = field(default_factory=dict)             # dst → (来源 id, FileSpec)
    entries: dict = field(default_factory=dict)
    manifests: dict = field(default_factory=dict)         # 模块 id → modules.json 中的附加字段
    runtime_config: dict = field(default_factory=dict)    # 文件名 → (来源 id, 内容)
    inspect_commands: dict = field(default_factory=dict)  # 键 → (来源 id, CommandSpec)
    knowledge_assembly: Optional[dict] = None
    skills: dict = field(default_factory=dict)            # 技能名 → 模块 id
    hooks: dict = field(default_factory=dict)             # 事件名 → 条目数组，按 MERGE_ORDER 依次追加


def _conflict(what: str, key: str, first: str, second: str) -> Issue:
    return error("MODULE_CONFLICT", f"{what} {key} 同时来自 {first} 和 {second}",
                 hint="这是脚手架模块之间的冲突，请向脚手架反馈")


def merge(contributions: dict) -> tuple[Merged, list[Issue]]:
    merged = Merged()
    issues: list[Issue] = []
    for source in MERGE_ORDER:
        contribution = contributions.get(source)
        if contribution is None:
            continue
        for spec in contribution.files:
            if spec.dst in merged.files:
                issues.append(_conflict("文件", spec.dst, merged.files[spec.dst][0], source))
                continue
            merged.files[spec.dst] = (source, spec)
        for key, value in contribution.entries.items():
            if key in CORE_ENTRY_KEYS or key in merged.entries:
                issues.append(_conflict("看板入口", key, "core" if key in CORE_ENTRY_KEYS else "其他模块", source))
                continue
            merged.entries[key] = value
        if contribution.manifest:
            if "enabled" in contribution.manifest or "version" in contribution.manifest:
                issues.append(_conflict("modules.json 字段", f"{source}.enabled/version", "core", source))
            merged.manifests[source] = dict(contribution.manifest)
        for name, value in contribution.runtime_config.items():
            if name in merged.runtime_config:
                issues.append(_conflict("编译配置", f"runtime/config/{name}.json", merged.runtime_config[name][0],
                                        source))
                continue
            merged.runtime_config[name] = (source, value)
        for key, spec in contribution.inspect_commands.items():
            if key in merged.inspect_commands:
                issues.append(_conflict("宿主命令", key, merged.inspect_commands[key][0], source))
                continue
            merged.inspect_commands[key] = (source, spec)
        if contribution.knowledge_assembly is not None:
            if merged.knowledge_assembly is not None:
                issues.append(_conflict("knowledgeAssembly", "session.json", "其他模块", source))
            merged.knowledge_assembly = contribution.knowledge_assembly
        for skill in contribution.skills:
            if skill in merged.skills:
                issues.append(_conflict("技能", skill, merged.skills[skill], source))
                continue
            merged.skills[skill] = source
        for event, items in contribution.hooks.items():
            merged.hooks.setdefault(event, []).extend(items)
    return merged, issues
