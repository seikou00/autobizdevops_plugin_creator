"""package：check（只把 TODO_PLACEHOLDER 升为 error），递增 plugin.version 并重新生成，再按打包规则写 zip（output-spec.md §1，D57）。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from scaffold.build import customize, emit
from scaffold.build.framework import plugin_manifest
from scaffold.build.manifest import MANIFEST, read_manifest
from scaffold.commands import CommandResult
from scaffold.lib import derive, fsio, jsonedit, jsonschema
from scaffold.lib.tree import Tree

ENTRY = "plugin.scaffold.json"
PLUGIN_MANIFEST = "plugin.json"
RUNTIME_CONFIG = "runtime/config/runtime.json"
BUMPS = ("patch", "minor", "major", "none")

RECORDED_ROOTS = ("plugin.json", "board_core/", "runtime/")
WHOLE_DIRS = ("skills", "hooks", "agents")
NODE_MODULES = "runtime/knowledge/node_modules"
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
    if knowledge_enabled:
        # collector 的 Node 依赖由 doctor 安装，不归 build-manifest 记录，整个目录随包带上（README §9 第 7 条）
        for path in tree.walk(NODE_MODULES):
            if not _skipped(path):
                files.add(path)
    if knowledge_enabled and not knowledge_source:
        files.update(path for path in tree.walk("sys") if not _skipped(path))
    return sorted(files), sorted(set(skipped) - files)


def next_version(version: str, bump: str) -> str:
    """按 bump 递增 x.y.z；预发布后缀（-beta 等）一并去掉。"""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    major, minor, patch = (int(part) for part in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def bump_version(root: Path, bump: str):
    """改写入口文件的 plugin.version（保留原有格式），重新生成 plugin.json 和 build-manifest。

    返回 (旧版本, 新版本, 写入的文件, report)；report 有 error 时不写任何文件。
    """
    from scaffold.build.pipeline import build

    text = Tree(root).read_bytes(ENTRY).decode("utf-8")
    old = fsio.parse_json(text.encode("utf-8"))["plugin"]["version"]
    new = next_version(old, bump)
    data = jsonedit.set_member(text, "/plugin", "version", new).encode("utf-8")
    result = build(Tree(root, {ENTRY: data}), dry_run=True)
    if result.report.failed():
        return old, new, [], result.report
    fsio.atomic_write(root / ENTRY, data)
    written = [ENTRY] + emit.apply(result.plan, Tree(root), MANIFEST, fsio.dump_json(result.manifest))
    return old, new, written, result.report


def release_tree(tree: Tree, plugin_id: str, manifest: dict, source_plugin: dict) -> Tree:
    """发布包内统一身份，并同步更新归档文件的摘要。"""
    overrides = {}
    plugin_data = tree.read_bytes(PLUGIN_MANIFEST)
    plugin = fsio.parse_json(plugin_data)
    name = derive.prefixed_plugin_field(plugin["name"])
    if name != plugin["name"]:
        plugin["name"] = name
        plugin_data = overrides[PLUGIN_MANIFEST] = fsio.dump_json(plugin)
    record = customize.plugin_name_record(manifest["files"][PLUGIN_MANIFEST], plugin_manifest(source_plugin))
    manifest["files"][PLUGIN_MANIFEST] = record
    record["sha256"] = fsio.digest(plugin_data)
    edits = customize.edited(PLUGIN_MANIFEST, plugin, record)
    if edits:
        record["customized"] = {key: fsio.digest(value) for key, value in sorted(edits.items())}
    else:
        record.pop("customized", None)
    runtime = fsio.parse_json(tree.read_bytes(RUNTIME_CONFIG))
    if runtime.get("pluginId") != plugin_id:
        runtime["pluginId"] = plugin_id
        overrides[RUNTIME_CONFIG] = fsio.dump_json(runtime)
        manifest["files"][RUNTIME_CONFIG]["sha256"] = fsio.digest(overrides[RUNTIME_CONFIG])
    manifest["pluginId"] = plugin_id
    overrides[MANIFEST] = fsio.dump_json(manifest)
    return Tree(tree.root, overrides)


def write_zip(tree: Tree, plugin_id: str, files: list, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            info = zipfile.ZipInfo(f"{plugin_id}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, tree.read_bytes(rel))
    temporary.replace(output)


def package(root: Path, *, output: Path | None = None, bump: str = "patch") -> CommandResult:
    from scaffold.commands.check import check

    result = check(root, package_mode=True)
    if result.report.failed():
        return CommandResult(result.report)
    tree = Tree(root)
    entry = fsio.parse_json(tree.read_bytes(ENTRY))
    source_id = entry["plugin"]["id"]
    plugin_id = derive.prefixed_plugin_field(source_id)
    id_schema = jsonschema.load_schema("plugin-scaffold.schema.json")["definitions"]["plugin"]["properties"]["id"]
    for _, reason in jsonschema.validate(plugin_id, id_schema):
        result.report.add("error", "PACKAGE_PLUGIN_ID", f"加上 {derive.PLUGIN_PREFIX} 后的插件 ID 无效：{reason}",
                          file=ENTRY, pointer="/plugin/id")
    plugin_name = fsio.parse_json(tree.read_bytes(PLUGIN_MANIFEST)).get("name")
    if not isinstance(plugin_name, str) or not plugin_name.strip():
        result.report.add("error", "PACKAGE_PLUGIN_NAME", "插件名称不能为空", file=PLUGIN_MANIFEST, pointer="/name")
    if result.report.failed():
        return CommandResult(result.report)
    if plugin_id != source_id:
        result.report.add("warning", "PACKAGE_PLUGIN_ID_CHANGED", f"发布包使用插件 ID {plugin_id}。"
                          f"已有项目的状态若记录了旧 ID {source_id}，需迁移后才能用新版读写",
                          file=ENTRY, pointer="/plugin/id")
    written = []
    version = None
    if bump != "none":
        old, new, written, report = bump_version(root, bump)
        result.report.extend([issue for issue in report.issues if issue not in result.report.issues])
        if report.failed():
            return CommandResult(result.report)
        version = {"from": old, "to": new}
    tree = Tree(root)
    entry = fsio.parse_json(tree.read_bytes(ENTRY))
    manifest = read_manifest(tree)
    modules = (entry.get("modules") or {})
    knowledge_source = False
    if "knowledge" in modules:
        rel = modules["knowledge"][2:] if modules["knowledge"].startswith("./") else modules["knowledge"]
        knowledge_source = "source" in (fsio.parse_json(tree.read_bytes(rel)) or {})
    files, skipped = collect(root, entry, manifest, knowledge_enabled="knowledge" in modules,
                             knowledge_source=knowledge_source)
    plugin = entry["plugin"]
    target = output or (root / "dist" / f"{plugin_id}-{plugin['version']}.zip")
    target = target if target.is_absolute() else Path.cwd() / target
    write_zip(release_tree(tree, plugin_id, manifest, plugin), plugin_id, files, target)
    try:
        shown = target.relative_to(root).as_posix()
    except ValueError:
        shown = target.as_posix()
    lines = [f"版本 {version['from']} → {version['to']}"] if version else []
    lines.append(f"已打包 {len(files)} 个文件：{shown}")
    return CommandResult(result.report, extra={"package": {"path": shown, "skipped": skipped, "version": version}},
                         written=written + [shown], text="\n".join(lines))

