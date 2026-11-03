"""写盘计划、漂移检查与写盘（scaffold.md 单元 8，D52）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold import resources
from scaffold.lib import fsio
from scaffold.lib.issues import Issue, error
from scaffold.modules import discover


@dataclass(frozen=True)
class PlannedFile:
    path: str
    ownership: str               # managed | module | generated | seeded | developer
    data: bytes
    source: str
    replaceable: bool = False
    region: str | None = None
    recorded: bool = True        # 记入 build-manifest


@dataclass
class WritePlan:
    files: dict = field(default_factory=dict)
    keep: set = field(default_factory=set)      # 插件替换过的 replaceable 文件，不覆盖

    def add(self, planned: PlannedFile) -> None:
        self.files[planned.path] = planned


def _source_bytes(source: str, spec) -> bytes:
    if spec.content is not None:
        return spec.content.encode("utf-8") if isinstance(spec.content, str) else spec.content
    if spec.src.startswith("files/"):
        return resources.read_bytes(f"{discover()[source].package}/{spec.src}")
    return resources.read_bytes(spec.src)


def plan_files(merged, skill_files: list, board_core: dict) -> WritePlan:
    plan = WritePlan()
    for path, (source, spec) in merged.files.items():
        plan.add(PlannedFile(path, spec.ownership, _source_bytes(source, spec), source, spec.replaceable))
    for name, (source, value) in merged.runtime_config.items():
        if name == "session":
            value = {**value, "knowledgeAssembly": merged.knowledge_assembly}
        plan.add(PlannedFile(f"runtime/config/{name}.json", "generated", fsio.dump_json(value), source))
    for path, data in board_core.items():
        plan.add(PlannedFile(path, "generated", data, "framework"))
    for skill in skill_files:
        plan.add(PlannedFile(skill.path, "seeded" if skill.recorded else "developer", skill.data, "skills",
                             region=skill.region, recorded=skill.recorded))
    return plan


def check_drift(plan: WritePlan, tree, previous: dict | None, *, force: bool) -> list[Issue]:
    """managed、module 文件：磁盘内容既不等于记录也不等于新内容时报 DRIFT_MANAGED。

    replaceable 的文件与记录不符时视为插件的替换：保留，不报。
    """
    issues = []
    recorded = (previous or {}).get("files", {})
    for path, planned in sorted(plan.files.items()):
        if planned.ownership not in ("managed", "module"):
            continue
        disk = tree.read_bytes(path)
        if disk is None or fsio.same_content(disk, planned.data):
            continue
        record = recorded.get(path, {}).get("sha256")
        if planned.replaceable:
            if record is None or fsio.digest(disk) != record:
                plan.keep.add(path)
            continue
        if record is not None and fsio.digest(disk) == record:
            continue
        if not force:
            issues.append(error("DRIFT_MANAGED", f"{path} 归脚手架托管，但内容被改过", file=path,
                                hint="不要手改托管文件；确认要覆盖时执行 autobiz-plugin doctor --force"))
    return issues


def changed_files(plan: WritePlan, tree) -> list:
    result = []
    for path, planned in sorted(plan.files.items()):
        if path in plan.keep:
            continue
        if not fsio.same_content(tree.read_bytes(path), planned.data):
            result.append(path)
    return result


def apply(plan: WritePlan, tree, manifest_path: str, manifest_data: bytes) -> list:
    """只写内容有变化的文件，逐个原子替换；build-manifest 最后写（D52）。"""
    written = []
    for path in changed_files(plan, tree):
        fsio.atomic_write(tree.path(path), plan.files[path].data)
        written.append(path)
    if not fsio.same_content(tree.read_bytes(manifest_path), manifest_data):
        fsio.atomic_write(tree.path(manifest_path), manifest_data)
        written.append(manifest_path)
    return written
