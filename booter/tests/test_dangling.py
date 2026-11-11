"""悬空引用检查（D71）：SKILL.md 正文引用的 templates/、references/、scripts/、hooks/ 等文件要真的在插件里。"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from tests.helpers import cli, new_from_example, temp_dir, copy_example
from scaffold.build.dangling import absolute_references, dangling_refs, references
from scaffold.lib.tree import Tree

CODE = "SKILL_REF_DANGLING"


def dangling(payload: dict) -> list:
    return [issue for issue in payload["issues"] if issue["code"] == CODE]


class ReferencesTest(unittest.TestCase):
    def found(self, body: str, directory: str = "skills/autodev/plan") -> dict:
        text = "---\nname: plan\ndescription: 计划\n---\n" + body
        return {token: candidates for token, (candidates, _) in references(text, directory).items()}

    def test_plugin_root_reference_is_resolved_from_plugin_root(self):
        found = self.found('python "${pluginPath}/hooks/stage_gate.py" validate\n读 `${pluginPath}/read_state.py`。\n')
        self.assertEqual(found, {"${pluginPath}/hooks/stage_gate.py": ["hooks/stage_gate.py"],
                                 "${pluginPath}/read_state.py": ["read_state.py"]})

    def test_relative_reference_looks_in_skill_group_skills_and_root(self):
        found = self.found("按 [模板](templates/plan.md) 写；先运行 hooks/check.py。\n")
        self.assertEqual(found["templates/plan.md"], ["skills/autodev/plan/templates/plan.md",
                                                      "skills/autodev/templates/plan.md", "skills/templates/plan.md",
                                                      "templates/plan.md"])
        self.assertEqual(found["hooks/check.py"][-1], "hooks/check.py")

    def test_parent_reference_is_resolved_from_skill_directory_only(self):
        found = self.found("见 `../references/guide.md` 和 ./scripts/run.sh。\n")
        self.assertEqual(found["../references/guide.md"], ["skills/autodev/references/guide.md"])
        self.assertEqual(found["./scripts/run.sh"][0], "skills/autodev/plan/scripts/run.sh")

    def test_skills_prefixed_reference_is_resolved_from_plugin_root(self):
        self.assertEqual(self.found("读 skills/references/ask.md\n"), {"skills/references/ask.md": ["skills/references/ask.md"]})

    def test_ignored_tokens(self):
        body = "\n".join([
            "产出 specs/**/*.md 和 templates/<name>.md，脚本在 scripts/...，放在 scripts/ 下。",
            "工程里的 src/hooks/useAuth.ts、/root/skills/scripts/a.py、https://example.com/scripts/a.js 不算。",
            'python "${pluginPath}/hooks/update_checkpoint.py" --checkpoint plan_done',
            "变量路径 ${feature}/references/a.md、${pluginPath}/hooks/${name}.py 不算。",
        ]) + "\n"
        self.assertEqual(self.found(body), {})

    def test_state_block_is_skipped_and_line_numbers_count_frontmatter(self):
        text = ("---\nname: plan\ndescription: 计划\n---\n<!-- plugin workflow: begin state -->\n"
                '`${pluginPath}/runtime/missing.py`\n<!-- plugin workflow: end state -->\n\n读 references/a.md\n')
        self.assertEqual({token: numbers for token, (_, numbers) in references(text, "skills/plan").items()},
                         {"references/a.md": [9]})


class AbsoluteReferencesTest(unittest.TestCase):
    def found(self, body: str) -> dict:
        return absolute_references("---\nname: plan\ndescription: 计划\n---\n" + body)

    def test_hard_coded_plugin_and_skill_locations_are_found(self):
        body = ("python /root/.openclaw/workspace/skills/password-encrypt/scripts/encrypt.py\n"
                "读 `~/.claude/skills/plan/references/a.md`，或 C:\\Users\\me\\plugin\\hooks\\gate.py、D:/plugin/templates/a.md。\n")
        self.assertEqual(self.found(body), {
            "/root/.openclaw/workspace/skills/password-encrypt/scripts/encrypt.py": [5],
            "~/.claude/skills/plan/references/a.md": [6],
            "C:\\Users\\me\\plugin\\hooks\\gate.py": [6],
            "D:/plugin/templates/a.md": [6],
        })

    def test_other_absolute_looking_tokens_are_ignored(self):
        body = "\n".join([
            "调用 /api/users/list，执行 /autodev-plan，见 https://example.com/skills/scripts/a.js。",
            "相对路径 skills/autodev/hooks/a.py、${pluginPath}/hooks/a.py、../references/a.md 不算。",
            "占位 /path/to/<plugin>/hooks/a.py、/opt/${name}/scripts/a.py，目录 /scripts 不算。",
        ]) + "\n"
        self.assertEqual(self.found(body), {})


class DanglingRefsTest(unittest.TestCase):
    def test_absolute_path_is_reported_with_same_named_plugin_file(self):
        root = temp_dir(self)
        (root / "skills/autodev/hooks/encrypt/scripts").mkdir(parents=True)
        (root / "skills/autodev/hooks/encrypt/scripts/encrypt.py").write_text("", "utf-8")
        (root / "skills/autodev/SKILL.md").write_text(
            "---\nname: autodev\ndescription: 开发\n---\n## 加密\npython /root/ws/skills/encrypt/scripts/encrypt.py\n", "utf-8")
        issues = dangling_refs(Tree(root))
        self.assertEqual([(issue.code, issue.level, issue.file) for issue in issues],
                         [("SKILL_REF_ABSOLUTE", "warning", "skills/autodev/SKILL.md")])
        self.assertIn("第 6 行（小节“加密”）", issues[0].message)
        self.assertIn("${pluginPath}/skills/autodev/hooks/encrypt/scripts/encrypt.py", issues[0].hint)

    def test_existing_planned_and_skipped_files_are_not_reported(self):
        root = temp_dir(self)
        (root / "skills/autodev/plan/templates").mkdir(parents=True)
        (root / "skills/autodev/plan/templates/plan.md").write_text("模板", "utf-8")
        (root / "hooks").mkdir()
        (root / "hooks/gate.py").write_text("", "utf-8")
        (root / "skills/autodev/plan/SKILL.md").write_text(
            "---\nname: plan\ndescription: 计划\n---\n## 步骤\n"
            "读 templates/plan.md 和 references/missing.md，运行 hooks/gate.py、`${pluginPath}/runtime/workflow/update_state.py`、"
            "`${pluginPath}/hooks/missing.py`；目录 templates/ok/ 和 references/none/。\n", "utf-8")
        (root / "skills/sync").mkdir()
        (root / "skills/sync/SKILL.md").write_text("---\nname: sync\ndescription: 同步\n---\n读 references/gone.md\n", "utf-8")
        issues = dangling_refs(Tree(root), planned=["runtime/workflow/update_state.py", "skills/autodev/plan/templates/ok/a.md"],
                               skip={"skills/sync/SKILL.md"})
        self.assertEqual({issue.code for issue in issues}, {CODE})
        self.assertEqual({issue.level for issue in issues}, {"warning"})
        self.assertEqual([issue.file for issue in issues], ["skills/autodev/plan/SKILL.md"] * 3)
        text = "\n".join(issue.message for issue in issues)
        for token in ("references/missing.md", "${pluginPath}/hooks/missing.py", "references/none/"):
            self.assertIn(token, text)
        self.assertIn("第 6 行（小节“步骤”）", issues[0].message)


class DoctorDanglingTest(unittest.TestCase):
    def test_doctor_and_check_report_dangling_reference_as_warning(self):
        root = new_from_example(self, "minimal")
        skill = root / "skills/autobiz/doc-draft/SKILL.md"
        skill.write_text(skill.read_text("utf-8") + "\n按 `templates/draft.md` 起草，完成前运行 "
                         '`python "${pluginPath}/hooks/draft_gate.py"`。\n', "utf-8")
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(sorted(issue["file"] for issue in dangling(payload)), [skill.relative_to(root).as_posix()] * 2)
        self.assertEqual({issue["level"] for issue in dangling(payload)}, {"warning"})
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(len(dangling(payload)), 2, payload)

        (skill.parent / "templates").mkdir()
        (skill.parent / "templates/draft.md").write_text("模板", "utf-8")
        (root / "hooks/draft_gate.py").write_text("", "utf-8")
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(dangling(payload), [])

    def test_first_doctor_does_not_report_files_it_is_about_to_generate(self):
        root = copy_example(self, "minimal", temp_dir(self) / "plugin")
        code, payload = cli("-C", str(root), "doctor", "--dry-run")
        self.assertEqual(code, 0, payload)
        self.assertEqual(dangling(payload), [])


class FullstackSkillsExampleTest(unittest.TestCase):
    """examples/fullstack-skills：全栈版的技能连同重构后的流程脚本（skills/scripts/flowlib/）一起搬来。"""

    def doctor(self, *, without=()) -> dict:
        root = copy_example(self, "fullstack-skills", temp_dir(self) / "plugin")
        for rel in without:
            target = root / rel
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        drop_knowledge(root)
        code, payload = cli("-C", str(root), "doctor", "--dry-run")
        self.assertEqual(code, 0, payload)
        return payload

    def test_every_reference_resolves(self):
        self.assertEqual(dangling(self.doctor()), [])

    def test_hard_coded_absolute_path_is_reported(self):
        issues = [issue for issue in self.doctor()["issues"] if issue["code"] == "SKILL_REF_ABSOLUTE"]
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("/root/.openclaw/workspace/skills/password-encrypt/scripts/password-encrypt.py", issues[0]["message"])
        self.assertIn("${pluginPath}/skills/autodev/password-encrypt/scripts/password-encrypt.py", issues[0]["hint"])

    def test_missing_scripts_and_templates_are_reported(self):
        payload = self.doctor(without=["skills/scripts/flowlib/stage_gate.py", "skills/autodev/autodev-plan/templates"])
        by_file = {}
        for issue in dangling(payload):
            by_file.setdefault(issue["file"], []).append(issue["message"])
        plan = "\n".join(by_file["skills/autodev/autodev-plan/SKILL.md"])
        self.assertIn("${pluginPath}/skills/scripts/flowlib/stage_gate.py", plan)
        self.assertIn("templates/plan-input.json", plan)
        self.assertIn("${pluginPath}/skills/scripts/flowlib/stage_gate.py",
                      "\n".join(by_file["skills/autodev/autodev-design/SKILL.md"]))


def drop_knowledge(root: Path) -> None:
    """不拉知识仓库，测试不联网。"""
    (root / "modules/knowledge.json").unlink()
    entry = root / "plugin.scaffold.json"
    entry.write_text(entry.read_text("utf-8").replace('    "knowledge": "./modules/knowledge.json",\n', ""), "utf-8")


if __name__ == "__main__":
    unittest.main()
