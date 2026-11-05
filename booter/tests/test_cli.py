"""CLI 的端到端测试：new → check → package，以及 lint 规则、doctor、add skill（interfaces.md §1）。"""

import json
import unittest
import zipfile

from tests.helpers import SIBLINGS, cli, new_from_example, temp_dir

ANSWERS = {
    "plugin": {"id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审"},
    "nodes": [
        {"id": "draft", "name": "起草", "stage": "biz", "seq": 1, "skill": "doc-draft", "outputs": ["DRAFT.md"]},
        {"id": "review", "name": "评审", "stage": "biz", "seq": 2, "skill": "doc-review", "outputs": ["REVIEW.md"]},
    ],
    "skills": {"doc-draft": None},
}


def codes(payload, level=None):
    return sorted({issue["code"] for issue in payload["issues"] if level is None or issue["level"] == level})


def fill_descriptions(root):
    for path in (root / "skills").rglob("SKILL.md"):
        text = path.read_text("utf-8").replace("[TODO: 做什么；在什么情况下使用]", "起草或评审文档时使用")
        path.write_text(text, "utf-8")


class NewAndPackageTest(unittest.TestCase):
    def new_plugin(self):
        root = temp_dir(self) / "doc-review"
        answers = root.parent / "answers.json"
        answers.write_text(json.dumps(ANSWERS, ensure_ascii=False), "utf-8")
        code, payload = cli("new", str(root), "--answers", str(answers), "--yes")
        self.assertEqual(code, 0, payload)
        return root

    def test_new_check_package(self):
        root = self.new_plugin()
        self.assertTrue((root / "hooks").is_dir())
        self.assertIn("./.scaffold/workflow.schema.json", (root / "workflow.json").read_text("utf-8"))
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["contract"]["ran"])
        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 1)
        self.assertIn("TODO_PLACEHOLDER", codes(payload, "error"))
        fill_descriptions(root)
        code, payload = cli("-C", str(root), "lint")
        self.assertIn("BUILD_STALE", codes(payload, "error"))
        self.assertEqual(cli("-C", str(root), "doctor")[0], 0)
        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 0, payload)
        with zipfile.ZipFile(root / payload["package"]["path"]) as archive:
            names = archive.namelist()
        self.assertTrue(all(name.startswith("doc-review/") for name in names))
        self.assertIn("doc-review/runtime/build-manifest.json", names)
        self.assertNotIn("doc-review/workflow.json", names)
        self.assertNotIn("doc-review/.scaffold/workflow.schema.json", names)
        self.assertEqual(names, sorted(names))
        board = json.loads((root / "runtime/config/board.json").read_text("utf-8"))
        self.assertEqual(board["nodes"]["biz"][0]["description"], "起草或评审文档时使用")

    def test_target_must_be_empty_and_usage_exit_code(self):
        root = temp_dir(self)
        (root / "x").write_text("x")
        code, payload = cli("new", str(root), "--yes")
        self.assertEqual(code, 2)
        self.assertEqual(codes(payload), ["USAGE"])

    def test_yes_needs_full_answers(self):
        root = temp_dir(self) / "p"
        code, payload = cli("new", str(root), "--yes")
        self.assertEqual(code, 2)
        self.assertEqual(codes(payload), ["USAGE"])
        self.assertFalse(root.exists())


class LintTest(unittest.TestCase):
    def plugin(self, workflow):
        root = temp_dir(self)
        (root / "plugin.scaffold.json").write_text(json.dumps({
            "scaffoldVersion": 1, "plugin": {"id": "p", "name": "P", "version": "0.1.0", "description": "d"}}), "utf-8")
        (root / "workflow.json").write_text(json.dumps(workflow), "utf-8")
        return root

    def test_core_rules(self):
        root = self.plugin({"nodes": {
            "biz": [{"id": "a", "seq": 5, "name": "A", "skill": "s-a", "outputs": ["PLAN.md", "x/../y.md"]}],
            "dev": [{"id": "a", "seq": 5, "name": "B", "skill": "s-a", "outputs": ["plan.md"]},
                    {"id": "c", "seq": 1, "name": "C", "skill": "s-c", "terminal": True, "outputs": ["c.md"]}]}})
        code, payload = cli("-C", str(root), "lint")
        self.assertEqual(code, 1)
        self.assertEqual(codes(payload, "error"), ["ARTIFACT_ID_CONFLICT", "NODE_DUP", "PATH_UNSAFE", "SEQ_DUP",
                                                   "SEQ_STAGE_ORDER", "SKILL_SHARED", "TERMINAL_INVALID"])

    def test_schema_errors_and_duplicate_keys(self):
        root = self.plugin({"nodes": {"biz": [{"id": "A", "seq": 1, "name": "x", "skill": "y"}]}})
        code, payload = cli("-C", str(root), "lint")
        self.assertEqual(codes(payload), ["INPUT_SCHEMA"])
        (root / "workflow.json").write_text('{"nodes": {}, "nodes": {}}', "utf-8")
        code, payload = cli("-C", str(root), "lint")
        self.assertIn("重复的键", payload["issues"][0]["message"])

    def test_identity_change_needs_flag(self):
        root = self.plugin({"nodes": {"biz": [{"id": "a", "seq": 1, "name": "A", "skill": "s-a"}]}})
        self.assertEqual(cli("-C", str(root), "doctor")[0], 0)
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        entry["plugin"]["id"] = "q"
        (root / "plugin.scaffold.json").write_text(json.dumps(entry), "utf-8")
        code, payload = cli("-C", str(root), "doctor")
        self.assertIn("PLUGIN_ID_CHANGED", codes(payload, "error"))
        code, payload = cli("-C", str(root), "doctor", "--allow-id-change")
        self.assertEqual(code, 0, payload)
        self.assertEqual(json.loads((root / "runtime/config/runtime.json").read_text("utf-8"))["pluginId"], "q")


class DoctorTest(unittest.TestCase):
    def test_node_removal_drops_state_block(self):
        root = new_from_example(self, "lite")
        workflow = json.loads((root / "workflow.json").read_text("utf-8"))
        workflow["nodes"]["dev"] = [node for node in workflow["nodes"]["dev"] if node["id"] != "code"]
        (root / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False), "utf-8")
        code, payload = cli("-C", str(root), "lint")
        self.assertIn("POLICY_NODE_UNKNOWN", codes(payload, "error"))
        session = json.loads((root / "modules/session.json").read_text("utf-8"))
        session["policies"]["nodes"]["dev"] = [item for item in session["policies"]["nodes"]["dev"] if item["id"] != "code"]
        (root / "modules/session.json").write_text(json.dumps(session, ensure_ascii=False), "utf-8")
        code, payload = cli("-C", str(root), "doctor", "--dry-run")
        self.assertEqual(payload["changes"]["nodes"]["removed"], ["code"])
        self.assertIn("CHECKPOINT_REMOVED", codes(payload, "warning"))
        self.assertEqual(payload["written"], [])
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["changes"]["skills"]["stateRemoved"], ["skills/autodev/autodev-code/SKILL.md"])
        self.assertNotIn("plugin workflow", (root / "skills/autodev/autodev-code/SKILL.md").read_text("utf-8"))

    def test_add_skill_from_reference_plugin(self):
        source = SIBLINGS / "autobizdevops_lite" / "skills" / "autodev-plan"
        if not source.is_dir():
            self.skipTest("没有 autobizdevops_lite 参考仓库")
        root = new_from_example(self, "lite")
        code, payload = cli("-C", str(root), "add", "skill", "autodev-plan", "--from", str(source))
        self.assertEqual(code, 0, payload)
        self.assertIn("LEGACY_ENTRY_REF", codes(payload, "warning"))
        text = (root / "skills/autodev/autodev-plan/SKILL.md").read_text("utf-8")
        self.assertIn("--checkpoint plan_done", text)
        code, payload = cli("-C", str(root), "check")
        self.assertIn("LEGACY_ENTRY_REF", codes(payload, "error"))


if __name__ == "__main__":
    unittest.main()
