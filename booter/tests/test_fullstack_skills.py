"""examples/fullstack-skills 的流程脚本：重构后不再依赖原插件的 board_core，状态读写都走运行框架。

原插件根目录 hooks/ 下的脚本大多是技能调用的流程脚本，重构后：
- hooks/ 只放 hooks.json 注册的宿主钩子；
- 流程脚本和它们共用的库放在 skills/scripts/flowlib/（技能集合根目录的共享资源，随包打包）；
- 节点契约（输入产物、校验器）由 flowlib/contracts.py 从 runtime/config/flow.json 和 flowlib/node_contracts.json 读取。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import cli, copy_example, temp_dir
from tests.test_dangling import drop_knowledge


class FullstackSkillsScriptsTest(unittest.TestCase):
    def setUp(self):
        self.root = copy_example(self, "fullstack-skills", temp_dir(self) / "plugin")
        drop_knowledge(self.root)
        code, payload = cli("-C", str(self.root), "doctor")
        self.assertEqual(code, 0, payload)
        self.workspace = temp_dir(self)
        (self.workspace / "demo").mkdir()
        self.env = {**{key: value for key, value in os.environ.items() if key not in ("AUTOBIZ_BOARD_ENDPOINT",)},
                    "PLUGIN_WORKSPACE": str(self.workspace), "PROJECT_DIR": "demo", "FEATURE_ID": "f1",
                    "PYTHONDONTWRITEBYTECODE": "1"}

    def run_py(self, script: str, *args, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-X", "utf8", str(self.root / script), *args], input=stdin.encode("utf-8"),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, cwd=str(self.workspace / "demo"))

    def json_of(self, script: str, *args) -> dict:
        completed = self.run_py(script, *args)
        return json.loads(completed.stdout.decode("utf-8"))

    def start_feature(self) -> Path:
        self.assertTrue(self.json_of("runtime/adapters/init_workspace.py", "--workspace", str(self.workspace),
                                     "--project", "demo")["ok"])
        self.assertTrue(self.json_of("runtime/adapters/init_feature.py", "--workspace", str(self.workspace),
                                     "--project", "demo", "--feature", "f1")["ok"])
        return self.workspace / "demo/.autobizdevops/features/f1"

    def test_no_script_depends_on_the_old_board_core(self):
        offenders = [path.relative_to(self.root).as_posix() for path in self.root.rglob("*.py")
                     if "from board_core" in path.read_text("utf-8-sig") or "import board_core" in path.read_text("utf-8-sig")]
        self.assertEqual(offenders, [])
        registered = json.loads((self.root / "hooks/hooks.json").read_text("utf-8"))
        scripts = {next(token for token in hook["command"].split() if token.endswith(".py"))
                   for items in registered.values() for item in items for hook in item["hooks"]}
        self.assertEqual([script for script in sorted(scripts) if not (self.root / script).is_file()], [])
        # hooks/ 根目录只剩注册了的钩子脚本，流程脚本都在 skills/scripts/flowlib/
        loose = {f"hooks/{path.name}" for path in (self.root / "hooks").glob("*.py")}
        self.assertEqual(loose - scripts, set())

    def test_state_next_skill_and_contract(self):
        self.start_feature()
        completed = self.run_py("skills/scripts/flowlib/read_state_json.py", "--feature", "f1")
        self.assertEqual(completed.stdout.decode().strip(), "prd_in_progress", completed.stderr.decode())
        route = self.json_of("skills/scripts/flowlib/resolve_next_skill.py", "--json")
        self.assertEqual((route["ok"], route["currentNodeId"], route["recommendedNextSkill"]),
                         (True, "prd", "autobiz-requirement-discuss"))
        completed = self.run_py("skills/scripts/flowlib/inspect_skill_contract.py", "autodev-plan", "--feature", "f1",
                                "--plain")
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertIn("无 design.md 时回到 /autodev-design", completed.stdout.decode())

    def test_guards_block_direct_state_edits_and_failed_validation(self):
        self.start_feature()
        payload = {"tool_name": "write_file", "cwd": str(self.workspace / "demo"),
                   "tool_input": {"file_path": ".autobizdevops/state.json"}}
        completed = self.run_py("hooks/state_write_guard.py", stdin=json.dumps(payload))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["decision"], "block")
        command = f'python -X utf8 "{self.root}/runtime/workflow/update_state.py" --feature f1 --checkpoint prd_done'
        completed = self.run_py("hooks/stage_gate_guard.py",
                                stdin=json.dumps({"tool_name": "execute", "tool_input": {"command": command}}))
        self.assertEqual(completed.returncode, 2, completed.stderr.decode())
        self.assertIn("节点校验未通过", json.loads(completed.stdout)["reason"])
        completed = self.run_py("hooks/human_gate_design_done.py", stdin=json.dumps(
            {"tool_name": "execute", "tool_input": {"command": command.replace("prd_done", "design_done")}}))
        self.assertEqual(json.loads(completed.stdout)["decision"], "human_gate")

    def test_rollback_reopens_through_the_runtime(self):
        feature_dir = self.start_feature()
        (feature_dir / "specs/a").mkdir(parents=True)
        for name in ("PRD.md", "UI_CONTEXT.json", "proposal.md", "specs/a/spec.md", "design.md"):
            (feature_dir / name).write_text("x", "utf-8")
        for checkpoint in ("prd_done", "specs_in_progress", "specs_done", "design_in_progress"):
            self.assertTrue(self.json_of("runtime/workflow/update_state.py", "--checkpoint", checkpoint)["ok"])
        result = self.json_of("skills/scripts/flowlib/rollback_stage.py", "--feature", "f1", "--stage", "dev.specs",
                              "--state-mode", "target_in_progress", "--apply", "--json")
        self.assertEqual((result["ok"], result["newCheckpoint"]), (True, "specs_in_progress"), result)
        self.assertEqual(sorted(result["deletedArtifacts"]), ["design.md", "proposal.md", "specs/a/spec.md"])
        state = json.loads((self.workspace / "demo/.autobizdevops/state.json").read_text("utf-8"))
        self.assertEqual(state["features"]["f1"]["checkpoint"], "specs_in_progress")
        events = (self.workspace / "demo/.autobizdevops/hooks.ndjson").read_text("utf-8")
        self.assertIn('"eventId": "stage-rollback"', events)


if __name__ == "__main__":
    unittest.main()
