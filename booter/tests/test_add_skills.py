"""add skills 的端到端行为：批量导入、单次生成和失败原子性。"""

from __future__ import annotations

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
        # 非技能目录和嵌套技能不是 collection 的直接技能子目录。
        write_skill(collection / "examples", "nested-skill")

        code, payload = cli("-C", str(root), "add", "skills", "--from", str(collection))

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["importedSkills"], sorted(LITE_SKILLS))
        for name in LITE_SKILLS:
            path = root / "skills" / name / "SKILL.md"
            self.assertIn(f"{name} 的正文。", path.read_text("utf-8"))
            self.assertIn(f"skills/{name}/SKILL.md", payload["written"])
        self.assertEqual((root / "skills/autodev-plan/references/guide.md").read_text("utf-8"), "计划指南")
        self.assertFalse((root / "skills/examples").exists())
        self.assertFalse((root / "skills/nested-skill").exists())

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


if __name__ == "__main__":
    unittest.main()
