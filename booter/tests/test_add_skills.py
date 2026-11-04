"""add skills 的端到端行为：批量导入、单次生成和失败原子性。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import cli, temp_dir
from scaffold.commands import edit


LITE_SKILLS = ("autobiz-prd", "autodev-code", "autodev-plan", "autodev-sepc")


def write_skill(collection: Path, name: str, *, body: str = "执行任务。") -> Path:
    source = collection / name
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} 的测试技能\n---\n\n{body}\n", "utf-8"
    )
    return source


def snapshot(root: Path) -> dict[str, bytes | None]:
    """同时记录目录和文件，确保失败时没有留下部分导入结果。"""
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


class AddSkillsTest(unittest.TestCase):
    def new_lite(self) -> Path:
        root = temp_dir(self) / "plugin"
        code, payload = cli("new", str(root), "--from", "lite", "--yes")
        self.assertEqual(code, 0, payload)
        return root

    def test_imports_all_direct_skills_and_reports_names_in_json(self):
        root = self.new_lite()
        collection = temp_dir(self) / "skills"
        for name in reversed(LITE_SKILLS):
            write_skill(collection, name, body=f"{name} 的正文。")
        (collection / "autodev-plan" / "references").mkdir()
        (collection / "autodev-plan" / "references" / "guide.md").write_text("计划指南", "utf-8")
        # 技能内部更深层的 SKILL.md 是技能自己的资源，不是单独的技能。
        write_skill(collection / "autodev-plan" / "variants", "deep")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["importedSkills"], sorted(LITE_SKILLS))
        # 平铺的技能集合导入后按节点阶段挪进分组目录（D64）
        for name in LITE_SKILLS:
            group = "autobiz" if name.startswith("autobiz") else "autodev"
            path = root / "skills" / group / name / "SKILL.md"
            self.assertIn(f"{name} 的正文。", path.read_text("utf-8"))
            self.assertIn(f"skills/{group}/{name}/SKILL.md", payload["written"])
            self.assertFalse((root / "skills" / name).exists())
        self.assertEqual(len(payload["changes"]["skills"]["moved"]), len(LITE_SKILLS))
        self.assertEqual((root / "skills/autodev/autodev-plan/references/guide.md").read_text("utf-8"), "计划指南")
        self.assertTrue((root / "skills/autodev/autodev-plan/variants/deep/SKILL.md").is_file())
        self.assertFalse((root / "skills/deep").exists())

    def test_calls_doctor_once_for_the_whole_collection(self):
        root = self.new_lite()
        collection = temp_dir(self) / "skills"
        write_skill(collection, "autobiz-prd")
        write_skill(collection, "autodev-plan")

        with patch.object(edit, "doctor", wraps=edit.doctor) as doctor:
            result = edit.add_skills(root, source=collection)

        self.assertFalse(result.report.failed(), result.report.to_json())
        doctor.assert_called_once()

    def test_invalid_later_skill_name_leaves_plugin_unchanged(self):
        root = self.new_lite()
        before = snapshot(root)
        collection = temp_dir(self) / "skills"
        write_skill(collection, "a-valid")
        write_skill(collection, "zz-Invalid")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 2, payload)
        self.assertEqual([issue["code"] for issue in payload["issues"]], ["USAGE"])
        self.assertEqual(snapshot(root), before)
        self.assertFalse((root / "skills/a-valid").exists())

    def test_duplicate_later_skill_leaves_plugin_unchanged(self):
        root = self.new_lite()
        existing_source = temp_dir(self) / "autodev-plan"
        existing_source.mkdir()
        (existing_source / "SKILL.md").write_text(
            "---\nname: autodev-plan\ndescription: 已导入的计划技能\n---\n\n已有正文。\n", "utf-8"
        )
        code, payload = cli("-C", str(root), "add", "skill", "autodev-plan", "--from", str(existing_source))
        self.assertEqual(code, 0, payload)
        before = snapshot(root)
        collection = temp_dir(self) / "skills"
        write_skill(collection, "a-valid")
        write_skill(collection, "autodev-plan", body="重复导入。")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 2, payload)
        self.assertEqual([issue["code"] for issue in payload["issues"]], ["USAGE"])
        self.assertEqual(snapshot(root), before)
        self.assertFalse((root / "skills/a-valid").exists())


    def write_agents(self) -> Path:
        agents = temp_dir(self) / "agents"
        agents.mkdir()
        (agents / "explore.md").write_text("探索子代理", "utf-8")
        (agents / "critic_autodev_plan_zh.md").write_text("计划评审子代理", "utf-8")
        return agents

    def test_without_agents_option_creates_no_agents_dir(self):
        root = self.new_lite()
        collection = temp_dir(self) / "skills"
        write_skill(collection, "autobiz-prd")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 0, payload)
        self.assertFalse((root / "agents").exists())

    def test_agents_option_copies_files_and_clears_missing_warning(self):
        root = self.new_lite()
        collection = temp_dir(self) / "skills"
        write_skill(collection, "autobiz-prd")
        agents = self.write_agents()

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection), "--agents", str(agents))

        self.assertEqual(code, 0, payload)
        self.assertEqual((root / "agents/explore.md").read_text("utf-8"), "探索子代理")
        self.assertIn("agents/critic_autodev_plan_zh.md", payload["written"])
        self.assertNotIn("SUBAGENT_FILE_MISSING", [issue["code"] for issue in payload["issues"]])

    def test_conflicting_agent_file_leaves_plugin_unchanged(self):
        root = self.new_lite()
        (root / "agents").mkdir()
        (root / "agents/explore.md").write_text("已有的探索子代理", "utf-8")
        before = snapshot(root)
        collection = temp_dir(self) / "skills"
        write_skill(collection, "autobiz-prd")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection),
                            "--agents", str(self.write_agents()))

        self.assertEqual(code, 2, payload)
        self.assertEqual(snapshot(root), before)

    def test_new_answers_import_agents(self):
        agents = self.write_agents()
        answers = temp_dir(self) / "answers.json"
        answers.write_text(json.dumps({"agents": str(agents)}), "utf-8")
        root = temp_dir(self) / "plugin"

        code, payload = cli("new", str(root), "--from", "lite", "--yes", "--answers", str(answers))

        self.assertEqual(code, 0, payload)
        self.assertEqual((root / "agents/explore.md").read_text("utf-8"), "探索子代理")
        self.assertNotIn("SUBAGENT_FILE_MISSING", [issue["code"] for issue in payload["issues"]])


class NestedCollectionTest(unittest.TestCase):
    """技能集合按插件 skills/ 的布局导入：一层分组、共享资源和 build 生成的空白技能。"""

    def new_plugin(self, template: str = "lite") -> Path:
        root = temp_dir(self) / "plugin"
        code, payload = cli("new", str(root), "--from", template, "--yes")
        self.assertEqual(code, 0, payload)
        return root

    def write_collection(self) -> Path:
        collection = temp_dir(self) / "skills"
        (collection / "references").mkdir(parents=True)
        (collection / "references/ask.md").write_text("共享提问规范", "utf-8")
        write_skill(collection, "autobiz-prd")
        group = collection / "autodev"
        group.mkdir()
        (group / "SKILL.md").write_text("---\nname: autodev\ndescription: 开发阶段\nversion: v1\n---\n\n总览。\n", "utf-8")
        (group / "hooks").mkdir()
        (group / "hooks/check.py").write_text("print('ok')\n", "utf-8")
        write_skill(group / "hooks", "password-encrypt")
        for name in ("autodev-sepc", "autodev-plan", "autodev-code"):
            write_skill(group, name, body=f"{name} 的正文，参考 skills/references/ask.md。")
        return collection

    def test_groups_and_shared_resources_keep_their_paths(self):
        root = self.new_plugin()
        code, payload = cli("-C", str(root), "add", "skills", "--from", str(self.write_collection()))

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["importedSkills"], ["autobiz-prd", "autodev-code", "autodev-plan", "autodev-sepc"])
        for name in ("autodev-sepc", "autodev-plan", "autodev-code"):
            self.assertIn(f"{name} 的正文", (root / f"skills/autodev/{name}/SKILL.md").read_text("utf-8"))
            # build 生成的空白技能被分组下的技能替换，否则会有两个同名候选
            self.assertFalse((root / f"skills/{name}").exists())
        self.assertEqual((root / "skills/references/ask.md").read_text("utf-8"), "共享提问规范")
        self.assertEqual((root / "skills/autodev/hooks/check.py").read_text("utf-8"), "print('ok')\n")
        self.assertTrue((root / "skills/autodev/hooks/password-encrypt/SKILL.md").is_file())
        self.assertIn("metadata:\n  version: v1", (root / "skills/autodev/SKILL.md").read_text("utf-8"))
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 0, payload)

    def test_group_dir_as_source_imports_as_that_group(self):
        root = self.new_plugin()
        code, payload = cli("-C", str(root), "add", "skills", "--from", str(self.write_collection() / "autodev"))

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["importedSkills"], ["autodev-code", "autodev-plan", "autodev-sepc"])
        self.assertTrue((root / "skills/autodev/autodev-plan/SKILL.md").is_file())
        self.assertTrue((root / "skills/autodev/SKILL.md").is_file())
        self.assertFalse((root / "skills/SKILL.md").exists())
        self.assertFalse((root / "skills/hooks").exists())

    def test_skips_skills_generated_by_modules(self):
        root = self.new_plugin()
        generated = (root / "skills/autobizdevops-artifact-sync/SKILL.md").read_bytes()
        collection = self.write_collection()
        write_skill(collection, "autobizdevops-artifact-sync", body="旧插件里的产物同步技能。")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 0, payload)
        self.assertNotIn("autobizdevops-artifact-sync", payload["importedSkills"])
        self.assertEqual((root / "skills/autobizdevops-artifact-sync/SKILL.md").read_bytes(), generated)

    def test_same_skill_in_two_groups_leaves_plugin_unchanged(self):
        root = self.new_plugin()
        before = snapshot(root)
        collection = self.write_collection()
        other = collection / "autoops"
        other.mkdir()
        (other / "SKILL.md").write_text("---\nname: autoops\ndescription: 运维阶段\n---\n", "utf-8")
        write_skill(other, "autodev-plan")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 2, payload)
        self.assertEqual(snapshot(root), before)

    def test_conflicting_shared_resource_leaves_plugin_unchanged(self):
        root = self.new_plugin()
        (root / "skills/references").mkdir()
        (root / "skills/references/ask.md").write_text("已有内容", "utf-8")
        before = snapshot(root)

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(self.write_collection()))

        self.assertEqual(code, 2, payload)
        self.assertEqual(snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
