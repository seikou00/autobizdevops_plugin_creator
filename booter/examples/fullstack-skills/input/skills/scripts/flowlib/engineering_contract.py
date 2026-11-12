"""Audit the actual agent, Workflow, policy and Runtime deployment together."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

FILES = ("skills/autodev/autodev-code/references/task-execution.md",
         "skills/scripts/flowlib/parallel_delivery.py", "skills/scripts/flowlib/parallel_cleanup.py", "skills/scripts/flowlib/parallel_repository.py",
         "skills/autodev/autodev-code/references/frontend-route.md",
         "skills/autodev/autodev-reviewer/SKILL.md", "skills/autodev/autodev-e2e/SKILL.md",
         "skills/autodev/autodev-e2e/reference/execution.md", "skills/scripts/flowlib/e2e_reuse.py", "skills/scripts/flowlib/compile_coverage.py",
         "agents/test-engineer.md", "hooks/augment_test_engineer_task_prompt.py", "hooks/hooks.json",
         "skills/scripts/flowlib/utest_policy.py", "skills/scripts/flowlib/utest_control.py", "hooks/utest_deadline_guard.py",
         "skills/scripts/flowlib/engineering_context.py", "skills/scripts/flowlib/engineering_facts.py", "skills/scripts/flowlib/engineering_cache.py",
         "skills/scripts/flowlib/engineering_dependencies.py", "skills/scripts/flowlib/engineering_environment.py", "skills/scripts/flowlib/runtime_guidance.py",
         "skills/scripts/flowlib/engineering_contract.py", "hooks/code_execution_guard.py", "hooks/frontend_route_write_guard.py",
         "skills/scripts/flowlib/utest_test_environment.py", "skills/scripts/flowlib/utest_workspace_binding.py",
         "skills/scripts/flowlib/parallel_batch_stage.py", "skills/scripts/flowlib/parallel_batch_scheduler.py", "skills/scripts/flowlib/run_utest_command.py",
         "skills/scripts/flowlib/utest_runtime.py", "skills/scripts/flowlib/utest_presets.py", "skills/scripts/flowlib/task_runner.py", "skills/scripts/flowlib/worktree_manager.py",
         "skills/autodev/autodev-code/SKILL.md", "skills/autodev/autodev-utest/SKILL.md",
         "skills/autodev/autodev-utest/reference/test-engineer-task-protocol.md",
         "agents/reviewer.md", "skills/scripts/flowlib/node_contracts.json", "runtime/config/flow.json", "skills/scripts/flowlib/workflow_launcher.py",
         "skills/scripts/flowlib/parallel_dispatch.py", "skills/scripts/flowlib/parallel_runtime.py", "skills/scripts/flowlib/parallel_integration.py",
         "skills/scripts/flowlib/parallel_merge_train.py", "skills/scripts/flowlib/parallel_batch_lifecycle.py", "skills/scripts/flowlib/parallel_final_verify.py",
         "skills/scripts/flowlib/parallel_evidence_aggregate.py", "skills/scripts/flowlib/contracts.py", "skills/scripts/flowlib/state_store.py",
         "skills/scripts/flowlib/evidence_integrity_gate.py", "skills/autodev/scripts/artifact_check.py", "skills/autodev/scripts/common.py",
         "skills/scripts/flowlib/batch_lease_manager.py", "skills/scripts/flowlib/query_json_fields.py", "skills/scripts/flowlib/code_task_context.py",
         "skills/scripts/flowlib/resolve_frontend_html_route.py", "skills/scripts/flowlib/utest_assignment_router.py",
         "skills/scripts/flowlib/inspect_test_environment.py", "skills/scripts/flowlib/validate_utest_source_bug.py",
         "skills/autodev/autodev-code/references/batch-workflow-guide.md",
         "skills/autodev/autodev-code/workflows/code-batched-execution.workflow.js")


def _local_imports(source: bytes, source_path: str) -> set[str]:
    dependencies = set()
    for node in ast.walk(ast.parse(source)):
        modules = []
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                package = source_path.removesuffix(".py").split("/")[:-1]
                module = ".".join([*package[:len(package) - node.level + 1], *filter(None, module.split("."))])
            modules = ([module + "." + alias.name for alias in node.names if alias.name != "*"]
                       if module in {"hooks", "flowlib"} else [module])
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        # flowlib 在 skills/scripts/ 下，hooks 在插件根目录下
        dependencies.update(("skills/scripts/" if module.startswith("flowlib.") else "") + module.replace(".", "/") + ".py"
                            for module in modules if module.startswith(("hooks.", "flowlib.")))
    return dependencies


def runtime_contract(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[3]
    hashes = {}
    pending = set(FILES)
    valid_python = True
    while pending:
        name = pending.pop()
        if name in hashes:
            continue
        path = root / name
        if not path.is_file():
            hashes[name] = None
            continue
        source = path.read_bytes()
        hashes[name] = hashlib.sha256(source).hexdigest()
        if name.endswith(".py"):
            try:
                pending.update(_local_imports(source, name) - hashes.keys())
            except SyntaxError:
                valid_python = False
    hashes = dict(sorted(hashes.items()))
    return {"version": "autodev.engineering.deployment.v2", "files": hashes,
            "complete": all(hashes.values()) and valid_python,
            "digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}
