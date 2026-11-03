"""产物同步模块：同步技能、同步配置 artifact-sync.json 与看板入口（input-config.md §4.5、output-spec.md §7.2）。"""

from __future__ import annotations

import re

from scaffold.build.contribute import Contribution, FileSpec
from scaffold.lib import fsio
from scaffold.lib.issues import error
from scaffold.modules import Module

FILE = "modules/artifactSync.json"
SOURCE_SKILL = "autobizdevops-artifact-sync"
SKILL_FILES = ("SKILL.md", "references/sync-runtime.md", "references/feature-api-detail.md", "references/ask-user-question.md",
               "scripts/sync_artifacts.py", "scripts/artifact_sync_utils.py")


def allowed_checkpoints(ir, options: dict) -> list:
    if "allowedCheckpoints" in options:
        return list(options["allowedCheckpoints"])
    excluded = set(options.get("excludeCheckpoints", []))
    return [checkpoint for checkpoint in ir.checkpoints_from(options["allowedFrom"]) if checkpoint not in excluded]


def sync_config(ir, options: dict) -> dict:
    wanted = options["artifacts"]
    stages: dict = {}
    registered = set()
    for node in ir.nodes:
        for output in node.outputs:
            path = ir.artifacts[output.artifact].label
            if path not in wanted or path in registered:
                continue
            registered.add(path)
            stages.setdefault(node.stage, {}).setdefault(node.id, {})[path] = wanted[path]
    return {
        "schemaVersion": 3,
        "allowedCheckpoints": allowed_checkpoints(ir, options),
        "uploadUrl": options["uploadUrl"],
        "maxFileSizeMiB": options["maxFileSizeMiB"],
        "stages": stages,
        "extraPaths": dict(options.get("extraPaths", {})),
    }


class ArtifactSyncModule(Module):
    def validate(self, ir, options, ctx):
        issues = []
        outputs = {artifact.label for artifact in ir.artifacts.values()}
        for path in options.get("artifacts", {}):
            if path not in outputs:
                issues.append(error("ARTIFACT_REF_UNKNOWN", f"artifacts 中的 {path} 不是任何节点 outputs 中的路径",
                                    file=FILE, pointer=f"/artifacts/{path.replace('~', '~0').replace('/', '~1')}",
                                    hint="key 要与 workflow.json 中 outputs 写的路径完全一致"))
        anchor = options.get("allowedFrom")
        if anchor is not None:
            checkpoint = ir.anchor_checkpoint(anchor)
            if checkpoint is None or checkpoint not in ir.checkpoint_chain:
                issues.append(error("MODULE_OPTION", f"allowedFrom 指向的 {anchor} 不是流程中的节点或 checkpoint",
                                    file=FILE, pointer="/allowedFrom",
                                    hint="写成 <nodeId>:<in_progress|done> 或 checkpoint 名"))
        for key in ("allowedCheckpoints", "excludeCheckpoints"):
            for index, checkpoint in enumerate(options.get(key, [])):
                if checkpoint not in ir.checkpoint_chain:
                    issues.append(error("MODULE_OPTION", f"{key} 中的 {checkpoint} 不是流程中的 checkpoint",
                                        file=FILE, pointer=f"/{key}/{index}"))
        skill = options.get("skillName")
        if skill in {node.skill for node in ir.nodes}:
            issues.append(error("MODULE_SKILL_CONFLICT", f"产物同步技能名 {skill} 与节点技能重名", file=FILE,
                                pointer="/skillName", hint="修改 skillName，或给节点换一个技能名"))
        return issues

    def contribute(self, ir, options, ctx):
        skill = options["skillName"]
        files = []
        for rel in SKILL_FILES:
            data = ctx.package_file(f"files/{SOURCE_SKILL}/{rel}")
            if rel == "SKILL.md" and skill != SOURCE_SKILL:
                text = data.decode("utf-8")
                text = re.sub(r"(?m)^name: .*$", f"name: {skill}", text, count=1).replace(SOURCE_SKILL, skill)
                data = text.encode("utf-8")
            files.append(FileSpec(f"skills/{skill}/{rel}", "module", content=data))
        files.append(FileSpec(f"skills/{skill}/config/artifact-sync.json", "generated",
                              content=fsio.dump_json(sync_config(ir, options))))
        entry = options.get("entry", {})
        entries = {}
        if entry.get("enabled", True):
            entries["artifact_sync"] = {"sync_type": entry.get("syncType"),
                                        "nextAction": {"slashSkill": skill, "userMessage": entry.get("userMessage"),
                                                       "dialogTips": entry.get("dialogTips")}}
        return Contribution(files=files, entries=entries, manifest={"skill": skill}, skills=[skill])
