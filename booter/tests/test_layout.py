"""节点技能按阶段放进分组目录（D64）：skills/autobiz|autodev|autoops/<技能>/，doctor 挪动并改引用。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import cli, new_from_example


class SkillLayoutTest(unittest.TestCase):
    def new_lite(self) -> Path:
        return new_from_example(self, "lite")

    def test_blank_skills_are_created_in_stage_groups(self):
        root = self.new_lite()
        self.assertTrue((root / "skills/autobiz/autobiz-prd/SKILL.md").is_file())
        for skill in ("autodev-sepc", "autodev-plan", "autodev-code"):
            self.assertTrue((root / f"skills/autodev/{skill}/SKILL.md").is_file())
        flow = json.loads((root / "runtime/config/flow.json").read_text("utf-8"))
        self.assertEqual(flow["nodes"][0]["skillDir"], "skills/autobiz/autobiz-prd")
        # 模块生成的技能不按阶段分组
        self.assertTrue((root / "skills/autobizdevops-artifact-sync/SKILL.md").is_file())

    def test_doctor_moves_flat_skills_and_rewrites_references(self):
        root = self.new_lite()
        old = root / "skills/autodev/autodev-plan"
        flat = root / "skills/autodev-plan"
        old.rename(flat)
        (flat / "references").mkdir()
        (flat / "references/guide.md").write_text("计划指南", "utf-8")
        text = (flat / "SKILL.md").read_text("utf-8")
        (flat / "SKILL.md").write_text(text + "\n读取 `${pluginPath}/skills/autodev-plan/references/guide.md`。\n", "utf-8")
        shared = root / "skills/references"
        shared.mkdir()
        (shared / "index.md").write_text("计划见 skills/autodev-plan/SKILL.md；myskills/autodev-plan/x 不动", "utf-8")

        code, payload = cli("-C", str(root), "lint")
        self.assertIn("SKILL_LAYOUT", [issue["code"] for issue in payload["issues"]])

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["changes"]["skills"]["moved"],
                         [{"from": "skills/autodev-plan", "to": "skills/autodev/autodev-plan"}])
        self.assertFalse(flat.exists())
        moved = (root / "skills/autodev/autodev-plan/SKILL.md").read_text("utf-8")
        self.assertIn("${pluginPath}/skills/autodev/autodev-plan/references/guide.md", moved)
        self.assertIn("plugin workflow: begin state", moved)
        self.assertEqual((root / "skills/autodev/autodev-plan/references/guide.md").read_text("utf-8"), "计划指南")
        self.assertEqual((shared / "index.md").read_text("utf-8"),
                         "计划见 skills/autodev/autodev-plan/SKILL.md；myskills/autodev-plan/x 不动")
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 0, payload)

    def test_stage_change_moves_skill_to_the_new_group(self):
        root = self.new_lite()
        workflow = json.loads((root / "workflow.json").read_text("utf-8"))
        prd = workflow["nodes"].pop("biz")[0]
        workflow["nodes"]["dev"].insert(0, prd)
        (root / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False), "utf-8")

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertTrue((root / "skills/autodev/autobiz-prd/SKILL.md").is_file())
        self.assertFalse((root / "skills/autobiz").exists())

    def test_existing_target_dir_is_a_conflict(self):
        root = self.new_lite()
        (root / "skills/autodev/autodev-plan").rename(root / "skills/autodev-plan")
        (root / "skills/autodev/autodev-plan").mkdir()
        (root / "skills/autodev/autodev-plan/notes.md").write_text("占位", "utf-8")

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 1, payload)
        self.assertIn("SKILL_LAYOUT_CONFLICT", [issue["code"] for issue in payload["issues"]])
        self.assertTrue((root / "skills/autodev-plan/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
