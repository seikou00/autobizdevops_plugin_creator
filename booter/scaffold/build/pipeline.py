"""build 流水线：load → normalize → lint → compile → contribute → merge → 写盘计划 → 漂移检查 → 写盘。

任何一步有 error 都返回，不写文件（interfaces.md §1.2）。CLI 不单独提供 build，由 doctor、new 等调用（D54）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold.build import emit, framework, lint, skills
from scaffold.build.compile import compile_ir
from scaffold.build.contribute import merge
from scaffold.build.load import load
from scaffold.build.manifest import MANIFEST, make_manifest, read_manifest
from scaffold.build.normalize import normalize
from scaffold.build.versions import VersionChanges, compare_versions
from scaffold.lib import fsio
from scaffold.lib.issues import Report
from scaffold.lib.tree import Tree
from scaffold.modules import context, enabled_modules


@dataclass
class BuildResult:
    report: Report
    tree: Tree
    normalized: object = None
    previous: dict | None = None
    skill_dirs: dict = field(default_factory=dict)
    ir: object = None
    modules: dict = field(default_factory=dict)
    plan: emit.WritePlan | None = None
    manifest: dict | None = None
    skills: skills.SkillChanges | None = None
    versions: VersionChanges = field(default_factory=VersionChanges)
    written: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.report.failed()


def analyze(tree: Tree, *, stale: bool = True, allow: frozenset = frozenset()) -> BuildResult:
    """lint 的全部内容：load → normalize → lint_core → compile → lint_modules。不写文件。"""
    result = BuildResult(Report(), tree)
    inputs, issues = load(tree)
    result.report.extend(issues)
    if inputs is None:
        return result
    result.normalized = normalize(inputs)
    result.previous = read_manifest(tree)
    result.skill_dirs = lint.skill_dirs(result.normalized)
    result.versions, issues = compare_versions(result.previous, enabled_modules(result.normalized), allow=allow,
                                               report_upgrade=stale)
    result.report.extend(issues)
    ctx = lint.LintContext(result.normalized, result.previous, result.skill_dirs, allow)
    result.report.extend(lint.lint_core(ctx, stale=False))
    if not result.report.failed():
        result.ir = compile_ir(result.normalized, result.skill_dirs)
        result.modules = enabled_modules(result.normalized)
        contexts = {module_id: context(result.normalized, module) for module_id, module in result.modules.items()}
        result.report.extend(lint.lint_modules(result.ir, result.normalized, result.modules, contexts))
    if stale:
        # 过期不影响 IR 是否可靠，放在模块规则之后报，不挡住模块规则
        result.report.extend(lint.build_stale(ctx))
    return result


def build(tree: Tree, *, dry_run: bool = False, force: bool = False, allow: frozenset = frozenset(),
          stale: bool = False) -> BuildResult:
    result = analyze(tree, stale=stale, allow=allow)
    if result.report.failed():
        return result
    ir, normalized = result.ir, result.normalized
    contributions = {"framework": framework.framework_contribution(ir, normalized, result.skill_dirs)}
    for module_id, module in result.modules.items():
        contributions[module_id] = module.contribute(ir, normalized.modules[module_id], context(normalized, module))
    merged, issues = merge(contributions)
    result.report.extend(issues)
    if result.report.failed():
        return result
    skill_files, result.skills, descriptions = skills.plan_skills(ir, tree, result.skill_dirs, result.previous)
    board_core = framework.render_board_core(normalized.modules["board"], merged, result.modules)
    result.plan = emit.plan_files(merged, skill_files, board_core)
    result.report.extend(emit.check_drift(result.plan, tree, result.previous, force=force))
    if result.report.failed():
        return result
    result.manifest = make_manifest(ir, normalized, result.plan, result.modules, descriptions, result.previous)
    if not dry_run:
        result.written = emit.apply(result.plan, tree, MANIFEST, fsio.dump_json(result.manifest))
    return result
