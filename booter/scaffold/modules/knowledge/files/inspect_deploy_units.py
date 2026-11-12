"""deploy_units：解析知识清单，输出支持的系统和发布单元（interfaces.md §3.3.8）。

同时是知识模块的清单解析库：内置知识组装脚本在 collector 未命中时、sync_knowledge 校验克隆结果时都复用它。
清单格式（v1 只有 agents-manifest-v1）::

    {"schemaVersion": "…", "systems": [{"systemId": "LF39", "description": "…", "agentsPath": "LF39/AGENTS.md",
      "deployUnits": [{"deployUnitId": "LF39.18_Outservice", "description": "…", "agentsPath": "…"}]}]}

旧字段名 serviceUnits / serviceUnitId、systemName、name、agents 仍可解析。只读，不访问网络。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Dict, List, Optional, Sequence, Tuple  # noqa: E402

SCHEMA_VERSION = "autobizdevops.deploy-units.v1"
AGENTS_MD = "AGENTS.md"
FORMATS = ("agents-manifest-v1",)


class AgentsManifestError(Exception):
    """清单缺失或不符合格式。"""


@dataclass(frozen=True)
class DeployUnit:
    deploy_unit_id: str
    name: str = ""
    agents_rel: str = ""


@dataclass(frozen=True)
class SystemEntry:
    system_id: str
    system_name: str = ""
    agents_rel: str = ""
    deploy_units: Tuple[DeployUnit, ...] = ()

    def agents_relpath(self) -> str:
        return self.agents_rel or f"{self.system_id}/{AGENTS_MD}"


@dataclass(frozen=True)
class Manifest:
    schema_version: str
    systems: Tuple[SystemEntry, ...]
    duplicates: frozenset = frozenset()


def knowledge_config() -> dict:
    path = ROOT / "runtime" / "config" / "knowledge.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"root": "sys", "manifest": {"format": "agents-manifest-v1", "path": "agents.manifest.json"}}


def manifest_settings() -> Tuple[str, str]:
    manifest = knowledge_config().get("manifest") or {}
    return manifest.get("format", "agents-manifest-v1"), manifest.get("path", "agents.manifest.json")


def platform_candidates(raw: Optional[str]) -> List[str]:
    """把 --knowledge-path-platform 展开为候选目录。

    DevClaw 把 ${knowledgePath} 替换为项目绑定知识库的 JSON 数组 [{"id", "name", "path"}]，没有时为 "[]"；
    也接受单个目录。数组中路径含未替换占位符的项单独跳过。
    """
    value = (raw or "").strip()
    if not value:
        return []
    if not value.startswith("["):
        return [] if "${" in value else [value]
    try:
        entries = json.loads(value)
    except ValueError:
        return []
    if not isinstance(entries, list):
        return []
    paths = [entry["path"].strip() for entry in entries
             if isinstance(entry, dict) and isinstance(entry.get("path"), str)]
    return [path for path in paths if path and "${" not in path]


def _lists_any(knowledge_dir: Path, unit_ids: Sequence[str]) -> bool:
    try:
        pairs = unit_pairs(load_manifest(knowledge_dir, strict_duplicates=False))
    except (AgentsManifestError, OSError):
        return False
    return any(unit_id in pairs for unit_id in unit_ids)


def choose_knowledge_dir(knowledge_path: Optional[str], platform_path: Optional[str],
                         unit_ids: Sequence[str] = ()) -> Path:
    """按平台知识库、插件知识库的顺序匹配所选发布单元，无匹配时取首个候选。"""
    candidates = [Path(path).expanduser() for path in platform_candidates(platform_path)]
    chosen = (knowledge_path or "").strip()
    if not chosen or "${" in chosen:
        chosen = str(ROOT / knowledge_config().get("root", "sys"))
    candidates.append(Path(chosen).expanduser())
    if unit_ids:
        for candidate in candidates:
            if _lists_any(candidate, unit_ids):
                return candidate
    return candidates[0]


def safe_join(root: Path, rel: str) -> Path:
    if not rel or not isinstance(rel, str):
        raise AgentsManifestError("清单中的路径不能为空")
    candidate = Path(rel)
    if candidate.is_absolute():
        raise AgentsManifestError(f"清单中的路径不能是绝对路径: {rel}")
    resolved = (root / candidate).resolve()
    base = root.resolve()
    if resolved != base and base not in resolved.parents:
        raise AgentsManifestError(f"清单中的路径越出知识目录: {rel}")
    return resolved


def _text(raw: dict, keys, context: str) -> str:
    for key in keys:
        if key in raw:
            value = raw[key]
            if not isinstance(value, str):
                raise AgentsManifestError(f"{context}.{key} 必须是字符串")
            return value
    return ""


def parse_manifest(data, *, strict_duplicates: bool = True) -> Manifest:
    if not isinstance(data, dict):
        raise AgentsManifestError("清单的根必须是对象")
    schema_version = data.get("schemaVersion", "v1")
    if not isinstance(schema_version, str) or not schema_version:
        raise AgentsManifestError("schemaVersion 必须是非空字符串")
    raw_systems = data.get("systems")
    if not isinstance(raw_systems, list):
        raise AgentsManifestError("systems 必须是数组")
    systems = []
    seen_systems = set()
    owners: Dict[str, str] = {}
    duplicates = set()
    for index, raw in enumerate(raw_systems):
        context = f"systems[{index}]"
        if not isinstance(raw, dict):
            raise AgentsManifestError(f"{context} 必须是对象")
        system_id = raw.get("systemId")
        if not isinstance(system_id, str) or not system_id.strip():
            raise AgentsManifestError(f"{context}.systemId 必须是非空字符串")
        system_id = system_id.strip()
        if system_id in seen_systems:
            raise AgentsManifestError(f"systemId 重复: {system_id}")
        seen_systems.add(system_id)
        agents_rel = _text(raw, ("agentsPath", "agents"), context)
        if agents_rel:
            safe_join(Path("/__knowledge__"), agents_rel)
        raw_units = raw.get("deployUnits", raw.get("serviceUnits"))
        if not isinstance(raw_units, list):
            raise AgentsManifestError(f"{context}.deployUnits 必须是数组，系统 {system_id}")
        units = []
        for unit_index, raw_unit in enumerate(raw_units):
            unit_context = f"{context}.deployUnits[{unit_index}]"
            if not isinstance(raw_unit, dict):
                raise AgentsManifestError(f"{unit_context} 必须是对象")
            unit_id = raw_unit.get("deployUnitId", raw_unit.get("serviceUnitId"))
            if not isinstance(unit_id, str) or not unit_id.strip():
                raise AgentsManifestError(f"{unit_context}.deployUnitId 必须是非空字符串")
            unit_id = unit_id.strip()
            if unit_id in owners:
                if strict_duplicates:
                    raise AgentsManifestError(f"deployUnitId 全局重复: {unit_id}（系统 {owners[unit_id]} 与 {system_id}）")
                duplicates.add(unit_id)
            owners[unit_id] = system_id
            unit_rel = _text(raw_unit, ("agentsPath",), unit_context)
            if unit_rel:
                safe_join(Path("/__knowledge__"), unit_rel)
            units.append(DeployUnit(unit_id, _text(raw_unit, ("description", "name"), unit_context), unit_rel))
        systems.append(SystemEntry(system_id, _text(raw, ("description", "systemName"), context), agents_rel,
                                   tuple(units)))
    return Manifest(schema_version, tuple(systems), frozenset(duplicates))


def load_manifest(knowledge_dir: Path, *, strict_duplicates: bool = True) -> Manifest:
    manifest_format, manifest_rel = manifest_settings()
    if manifest_format not in FORMATS:
        raise AgentsManifestError(f"不支持的清单格式: {manifest_format}")
    path = safe_join(Path(knowledge_dir), manifest_rel)
    if not path.is_file():
        raise AgentsManifestError(f"知识目录中没有清单 {manifest_rel}，请先同步知识仓库: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as error:
        raise AgentsManifestError(f"清单 JSON 解析失败: {path}: {error}") from None
    return parse_manifest(data, strict_duplicates=strict_duplicates)


def unit_pairs(manifest: Manifest) -> Dict[str, Tuple[SystemEntry, DeployUnit]]:
    return {unit.deploy_unit_id: (system, unit) for system in manifest.systems for unit in system.deploy_units}


def systems_payload(knowledge_dir: Path, manifest: Manifest, *, display_root: str = "") -> Tuple[list, list]:
    """返回 (systems, supportedDeployUnits)；agentsPath 显示为 <知识目录名>/<相对路径>。"""
    prefix = display_root or Path(knowledge_dir).name
    systems, supported = [], []
    for system in manifest.systems:
        try:
            ready = safe_join(Path(knowledge_dir), system.agents_relpath()).is_file()
        except AgentsManifestError:
            ready = False
        units = []
        for unit in system.deploy_units:
            supported.append(unit.deploy_unit_id)
            units.append({"deployUnitId": unit.deploy_unit_id, "name": unit.name, "description": unit.name})
        systems.append({"systemId": system.system_id, "systemName": system.system_name, "agentsReady": ready,
                        "agentsPath": f"{prefix}/{system.agents_relpath()}".replace("\\", "/"),
                        "deployUnits": units})
    return systems, list(dict.fromkeys(supported))


def inspect(knowledge_path: Optional[str], platform_path: Optional[str], system_id: Optional[str] = None) -> dict:
    knowledge_dir = choose_knowledge_dir(knowledge_path, platform_path)
    manifest_format, manifest_rel = manifest_settings()
    manifest = load_manifest(knowledge_dir)
    systems, supported = systems_payload(knowledge_dir, manifest)
    if system_id:
        systems = [system for system in systems if system["systemId"] == system_id]
        supported = [unit["deployUnitId"] for system in systems for unit in system["deployUnits"]]
    return {"ok": True, "schemaVersion": SCHEMA_VERSION, "knowledgePath": str(knowledge_dir.resolve()),
            "manifest": manifest_rel, "manifestFormat": manifest_format, "systems": systems,
            "supportedDeployUnits": supported}


def main(argv=None) -> int:
    from runtime.common import cli

    parser = cli.ArgumentParser(description="解析知识清单，列出支持的发布单元")
    parser.add_argument("--knowledge-path")
    parser.add_argument("--knowledge-path-platform")
    parser.add_argument("--system")

    def action():
        args = parser.parse_args(argv)
        try:
            return inspect(args.knowledge_path, args.knowledge_path_platform, args.system)
        except AgentsManifestError as error:
            return {"ok": False, "errors": [str(error)]}

    return cli.run(action)


if __name__ == "__main__":
    sys.exit(main())
