"""runtime/build-manifest.json（output-spec.md §8）与“编译配置是否过期”的判断。"""

from __future__ import annotations

from scaffold import CORE_VERSION, SCAFFOLD_VERSION
from scaffold.build.framework import skill_dir
from scaffold.build.load import MODULE_KEYS
from scaffold.lib import fsio, skillmd

MANIFEST = "runtime/build-manifest.json"
SCHEMA = "autobiz.build-manifest.v1"


def read_manifest(tree) -> dict | None:
    data = tree.read_bytes(MANIFEST)
    if data is None:
        return None
    try:
        value = fsio.parse_json(data, MANIFEST)
    except fsio.JsonError:
        return None
    return value if isinstance(value, dict) and value.get("schema") == SCHEMA else None


def config_digests(inputs) -> dict:
    result = {}
    for key in ("entry", "workflow") + MODULE_KEYS:
        rel = inputs.files.get(key)
        if rel and rel in inputs.digests:
            result[rel] = inputs.digests[rel]
    return result


def description_key(path: str) -> str:
    return f"{path}#description"


def current_descriptions(tree, workflow_nodes, skill_dirs: dict) -> dict:
    """节点技能 SKILL.md 路径 → description；还没有 SKILL.md 的技能不列出。"""
    result = {}
    for node in workflow_nodes:
        path = f"{skill_dir(skill_dirs, node['skill'])}/SKILL.md"
        data = tree.read_bytes(path)
        if data is not None:
            result[path] = skillmd.description_of(skillmd.read_text(data))
    return result


def recorded_inputs(inputs, descriptions: dict) -> dict:
    result = config_digests(inputs)
    for path in sorted(descriptions):
        result[description_key(path)] = fsio.digest(descriptions[path] or "")
    return result


def stale_inputs(current: dict, previous: dict | None) -> list:
    if previous is None:
        return []
    recorded = previous.get("inputs", {})
    keys = list(dict.fromkeys(list(recorded) + list(current)))
    return [key for key in keys if recorded.get(key) != current.get(key)]


def make_manifest(ir, normalized, plan, modules: dict, descriptions: dict, previous: dict | None) -> dict:
    files = {}
    for path, planned in plan.files.items():
        if not planned.recorded:
            continue
        if planned.ownership == "seeded":
            files[path] = {"ownership": "seeded", "regions": {"state": planned.region}}
        else:
            files[path] = {"ownership": planned.ownership, "sha256": fsio.digest(planned.data)}
    tree = normalized.inputs.tree
    for path, record in (previous or {}).get("files", {}).items():
        if path in files or record.get("ownership") not in ("generated", "managed", "module"):
            continue
        if tree.is_file(path):
            files[path] = {**{key: value for key, value in record.items() if key != "inactive"}, "inactive": True}
    return {
        "schema": SCHEMA,
        "scaffoldVersion": SCAFFOLD_VERSION,
        "coreVersion": CORE_VERSION,
        "pluginId": ir.plugin["id"],
        "metaRoot": ir.runtime["metaRoot"],
        "modules": {module_id: modules[module_id].version for module_id in MODULE_KEYS if module_id in modules},
        "inputs": recorded_inputs(normalized.inputs, descriptions),
        "files": {path: files[path] for path in sorted(files)},
    }
