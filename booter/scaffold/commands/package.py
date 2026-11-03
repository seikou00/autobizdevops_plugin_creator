"""package：check（只把 TODO_PLACEHOLDER 升为 error）后按打包规则写 zip（output-spec.md §1，D57）。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from scaffold.build.manifest import MANIFEST, read_manifest
from scaffold.commands import CommandResult
from scaffold.lib import fsio
from scaffold.lib.tree import Tree

RECORDED_ROOTS = ("plugin.json", "board_core/", "runtime/")
WHOLE_DIRS = ("skills", "hooks", "agents")
SKIPPED_NAMES = ("__pycache__", ".DS_Store", "Thumbs.db")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _skipped(rel: str) -> bool:
    parts = rel.split("/")
    return any(part in SKIPPED_NAMES for part in parts) or rel.endswith(".pyc")


def collect(root: Path, entry: dict, manifest: dict | None, *, knowledge_enabled: bool, knowledge_source: bool):
    """按打包清单收集文件：返回 (相对路径列表, 跳过的文件)。"""
    tree = Tree(root)
    files = set()
    skipped = []
    records = (manifest or {}).get("files", {})
    inactive = {path for path, record in records.items() if record.get("inactive")}
    for path, record in records.items():
        if path.startswith(RECORDED_ROOTS) and not record.get("inactive") and (root / path).is_file():
            files.add(path)
    if (root / MANIFEST).is_file():
        files.add(MANIFEST)
    for top in ("board_core", "runtime"):
        for path in tree.walk(top):
            if path not in files:
                skipped.append(path)
    for directory in WHOLE_DIRS:
        for path in tree.walk(directory):
            if _skipped(path) or path in inactive:
                continue
            files.add(path)
    plugin = entry.get("plugin", {})
    for key in ("mcpServers", "hooks"):
        ref = plugin.get(key)
        if ref:
            rel = ref[2:] if ref.startswith("./") else ref
            if (root / rel).is_file():
                files.add(rel)
    if knowledge_enabled and not knowledge_source:
        files.update(path for path in tree.walk("sys") if not _skipped(path))
    return sorted(files), sorted(set(skipped) - files)


def write_zip(root: Path, plugin_id: str, files: list, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            info = zipfile.ZipInfo(f"{plugin_id}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (root / rel).read_bytes())
    temporary.replace(output)


def package(root: Path, *, output: Path | None = None) -> CommandResult:
    from scaffold.commands.check import check

    result = check(root, package_mode=True)
    if result.report.failed():
        return CommandResult(result.report)
    tree = Tree(root)
    entry = fsio.parse_json(tree.read_bytes("plugin.scaffold.json"))
    manifest = read_manifest(tree)
    modules = (entry.get("modules") or {})
    knowledge_source = False
    if "knowledge" in modules:
        rel = modules["knowledge"][2:] if modules["knowledge"].startswith("./") else modules["knowledge"]
        knowledge_source = "source" in (fsio.parse_json(tree.read_bytes(rel)) or {})
    files, skipped = collect(root, entry, manifest, knowledge_enabled="knowledge" in modules,
                             knowledge_source=knowledge_source)
    plugin = entry["plugin"]
    target = output or (root / "dist" / f"{plugin['id']}-{plugin['version']}.zip")
    target = target if target.is_absolute() else Path.cwd() / target
    write_zip(root, plugin["id"], files, target)
    try:
        shown = target.relative_to(root).as_posix()
    except ValueError:
        shown = target.as_posix()
    return CommandResult(result.report, extra={"package": {"path": shown, "skipped": skipped}}, written=[shown],
                         text=f"已打包 {len(files)} 个文件：{shown}")

