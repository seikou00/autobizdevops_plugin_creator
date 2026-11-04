"""P1 功能的测试：初始化向导、add node、module、simulate、版本升级、全栈版 v3 状态接续、插件开发技能的插件包。"""

import json
import sys
import unittest
import zipfile

from tests.contract.test_runtime import Workspace
from tests.helpers import REPO, cli, temp_dir
from scaffold.commands.new import new
from scaffold.lib import jsonedit
from scaffold.wizard import ScriptedPrompter

WIZARD = ["Doc Review", "Doc-Review-Kanban", None, "文档起草与评审",
          "draft", "起草", "biz", None, "doc-draft", "DRAFT.md", "Y",
          "review", "评审", "biz", None, "doc-review", "REVIEW.md", "N",
          None, None, None, "multi", "N", "N", "N",
          "N", "Y"]                                    # 全局钩子：performance-check 不启用，secrets-check 启用


def codes(payload, level=None):
    return sorted({issue["code"] for issue in payload["issues"] if level is None or issue["level"] == level})


def set_manifest(root, **values):
    path = root / "runtime/build-manifest.json"
    data = json.loads(path.read_text("utf-8"))
    data.update(values)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


class WizardTest(unittest.TestCase):
    def test_scripted_session_creates_plugin(self):
        root = temp_dir(self) / "p"
        prompter = ScriptedPrompter(WIZARD)
        result = new(root, prompter=prompter)
        self.assertFalse(result.report.failed(), result.report.to_text())
        self.assertIn("  已规范化为 doc-review", prompter.lines)
        workflow = json.loads((root / "workflow.json").read_text("utf-8"))
        self.assertEqual([node["id"] for node in workflow["nodes"]["biz"]], ["draft", "review"])
        self.assertIn('"outputs": ["DRAFT.md"]', (root / "workflow.json").read_text("utf-8"))
        self.assertTrue((root / "skills/autobiz/doc-draft/SKILL.md").is_file())
        self.assertEqual(json.loads((root / "modules/globalHooks.json").read_text("utf-8"))["hooks"], ["secrets-check"])
        self.assertTrue((root / "hooks/secrets-check/check_secrets.py").is_file())

    def test_conflicting_answers_are_asked_again(self):
        answers = list(WIZARD)
        answers[11:11] = ["draft"]                    # 第二个节点先给出重复的 id
        prompter = ScriptedPrompter(answers)
        self.assertFalse(new(temp_dir(self) / "p", prompter=prompter).report.failed())
        self.assertIn("  节点 id draft 已经用过了", prompter.lines)


class EditCommandsTest(unittest.TestCase):
    def lite(self):
        root = temp_dir(self) / "lite"
        self.assertEqual(cli("new", str(root), "--from", "lite", "--yes")[0], 0)
        return root

    def test_add_node_keeps_formatting(self):
        root = self.lite()
        before = (root / "workflow.json").read_text("utf-8")
        code, payload = cli("-C", str(root), "add", "node", "review", "--name", "评审", "--skill", "autodev-review",
                            "--stage", "dev", "--seq", "5", "--output", "REVIEW.md", "--optional-output", "notes/*.md")
        self.assertEqual(code, 0, payload)
        after = (root / "workflow.json").read_text("utf-8")
        self.assertTrue(after.startswith(before[:before.index('"id": "code"')]))
        node = json.loads(after)["nodes"]["dev"][-1]
        self.assertEqual(node["outputs"], ["REVIEW.md", {"path": "notes/*.md", "optional": True}])
        self.assertEqual(payload["changes"]["nodes"]["added"], ["review"])
        code, payload = cli("-C", str(root), "add", "node", "x", "--name", "X", "--skill", "x-skill", "--stage", "dev",
                            "--seq", "5")
        self.assertEqual(code, 1)
        self.assertIn("SEQ_DUP", codes(payload, "error"))
        self.assertNotIn('"id": "x"', (root / "workflow.json").read_text("utf-8"))

    def test_module_disable_enable_and_set(self):
        root = self.lite()
        code, payload = cli("-C", str(root), "module", "list")
        self.assertEqual([item["enabled"] for item in payload["modules"]], [True, True, True, True, False])  # globalHooks 默认不启用
        self.assertEqual(cli("-C", str(root), "module", "disable", "artifactSync")[0], 0)
        manifest = json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))
        self.assertTrue(manifest["files"]["skills/autobizdevops-artifact-sync/SKILL.md"]["inactive"])
        self.assertIn("MODULE_INACTIVE_FILES", codes(cli("-C", str(root), "lint")[1], "warning"))
        modules = json.loads((root / "board_core/modules.json").read_text("utf-8"))
        self.assertEqual(modules["modules"]["artifactSync"], {"enabled": False})
        self.assertNotIn("artifact_sync", modules)
        self.assertEqual(cli("-C", str(root), "module", "enable", "artifactSync")[0], 0)
        self.assertNotIn("MODULE_INACTIVE_FILES", codes(cli("-C", str(root), "lint")[1]))
        code, payload = cli("-C", str(root), "module", "enable", "knowledge", "--set", "assembly.assembler=devclaw")
        self.assertEqual(code, 0, payload)
        session = json.loads((root / "runtime/config/session.json").read_text("utf-8"))
        self.assertIsNone(session["knowledgeAssembly"])
        self.assertEqual(cli("-C", str(root), "module", "enable", "knowledge", "--set", "nope=1")[0], 2)
        self.assertEqual(cli("-C", str(root), "module", "disable", "board")[0], 2)

    def test_enable_artifact_sync_needs_anchor_and_prefills(self):
        root = temp_dir(self) / "m"
        answers = root.parent / "a.json"
        answers.write_text(json.dumps({"plugin": {"id": "m", "name": "M", "version": "0.1.0", "description": "d"},
                                       "nodes": [{"id": "a", "name": "A", "stage": "biz", "seq": 1, "skill": "s-a",
                                                  "outputs": ["A.md", "a.json"]}]}), "utf-8")
        self.assertEqual(cli("new", str(root), "--answers", str(answers), "--yes")[0], 0)
        self.assertEqual(cli("-C", str(root), "module", "enable", "artifactSync")[0], 2)
        code, payload = cli("-C", str(root), "module", "enable", "artifactSync", "--set", "allowedFrom=a:done")
        self.assertEqual(code, 0, payload)
        config = json.loads((root / "modules/artifactSync.json").read_text("utf-8"))
        self.assertEqual(config["artifacts"], {"A.md": "[TODO: 简述]"})
        self.assertIn("TODO_PLACEHOLDER", codes(cli("-C", str(root), "check")[1]))


class SimulateTest(unittest.TestCase):
    def test_simulate_stops_and_warns_when_stale(self):
        root = temp_dir(self) / "full"
        self.assertEqual(cli("new", str(root), "--from", "fullstack", "--yes")[0], 0)
        code, payload = cli("-C", str(root), "simulate", "--to", "plan_done")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["simulation"]["stoppedAt"], "plan_done")
        workflow = root / "workflow.json"
        workflow.write_text(workflow.read_text("utf-8").replace('"name": "归档"', '"name": "收尾"'), "utf-8")
        code, payload = cli("-C", str(root), "simulate")
        self.assertEqual(code, 0)
        self.assertTrue(payload["simulation"]["stale"])
        self.assertEqual(payload["simulation"]["nodes"][-1]["status"], "archived")
        self.assertEqual(cli("-C", str(root), "simulate", "--to", "nope")[0], 2)


class VersionTest(unittest.TestCase):
    def plugin(self):
        root = temp_dir(self) / "lite"
        self.assertEqual(cli("new", str(root), "--from", "lite", "--yes")[0], 0)
        return root

    def test_same_major_upgrade(self):
        root = self.plugin()
        set_manifest(root, scaffoldVersion="0.9.0")
        self.assertIn("SCAFFOLD_VERSION_CHANGED", codes(cli("-C", str(root), "lint")[1], "warning"))
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["changes"]["versions"]["scaffold"], {"from": "0.9.0", "to": "1.0.0"})
        self.assertEqual(codes(cli("-C", str(root), "lint")[1], "warning").count("SCAFFOLD_VERSION_CHANGED"), 0)

    def test_major_change_and_outdated(self):
        root = self.plugin()
        set_manifest(root, coreVersion="0.9.0")
        code, payload = cli("-C", str(root), "doctor")
        self.assertIn("CORE_MAJOR_CHANGED", codes(payload, "error"))
        self.assertEqual(cli("-C", str(root), "doctor", "--allow-major-upgrade")[0], 0)
        set_manifest(root, coreVersion="1.1.0")
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("SCAFFOLD_OUTDATED", codes(payload, "error"))
        entry = root / "plugin.scaffold.json"
        entry.write_text(entry.read_text("utf-8").replace('"scaffoldVersion": 1', '"scaffoldVersion": 2'), "utf-8")
        self.assertEqual(codes(cli("-C", str(root), "lint")[1]), ["SCAFFOLD_OUTDATED"])


class LegacyStateTest(unittest.TestCase):
    def test_v3_state_is_read_and_upgraded_on_first_write(self):
        ws = Workspace(self, "fullstack")
        ws.meta.mkdir(parents=True)
        v3 = {"schemaVersion": "autobizdevops.state.v3", "features": {
            "f1": {"feature": "f1", "checkpoint": "plan_in_progress", "stage": "Plan", "workflowTemplate": "lean",
                   "workflowNodes": ["biz.prd", "dev.plan"]},
            "f2": "needs_fix",
            "f3": {"feature": "f3", "checkpoint": "detail_design_in_progress"}}}
        (ws.meta / "state.json").write_text(json.dumps(v3, ensure_ascii=False), "utf-8")
        run = ws.run("f1")
        self.assertEqual(run["currentNodeId"], "plan")
        stranded = ws.run("f2")
        self.assertTrue(stranded["readOnly"])
        self.assertEqual(stranded["currentNodeStatus"], "unknown")
        ws.write("PLAN.md", feature="f1")
        ws.write("plan.json", "{}\n", feature="f1")
        code, payload, _ = ws.update("plan_done", feature="f1")
        self.assertEqual(code, 0, payload)
        state = json.loads((ws.meta / "state.json").read_text("utf-8"))
        self.assertEqual((state["schemaVersion"], state["pluginId"]), (1, "autobizdevops-plugin"))
        self.assertEqual(state["features"]["f1"]["workflowTemplate"], "standard")
        self.assertEqual(state["features"]["f1"]["legacyWorkflowTemplate"], "lean")
        self.assertEqual(state["features"]["f3"]["checkpoint"], "detail_design_in_progress")
        self.assertTrue((ws.meta / "state.v3.bak.json").is_file())
        code, payload, _ = ws.update("specs_in_progress", "--reopen", "--reason", "x", feature="f3")
        self.assertEqual(code, 1)
        self.assertIn("只能查看", payload["errors"][0])


class JsonEditTest(unittest.TestCase):
    def test_edits_keep_other_bytes(self):
        text = '{\r\n  "a": [1, 2],\r\n  "b": { "c": 1 }\r\n}\r\n'
        self.assertEqual(jsonedit.insert_item(text, "/a", 1, 9), '{\r\n  "a": [1, 9, 2],\r\n  "b": { "c": 1 }\r\n}\r\n')
        self.assertEqual(jsonedit.set_member(text, "/b", "d", True), '{\r\n  "a": [1, 2],\r\n  "b": { "c": 1, "d": true }\r\n}\r\n')
        self.assertEqual(jsonedit.remove_member(text, "", "a"), '{\r\n  "b": { "c": 1 }\r\n}\r\n')
        self.assertEqual(json.loads(jsonedit.set_member(text, "", "e", {"f": [1]}))["e"], {"f": [1]})


class CreatorPackageTest(unittest.TestCase):
    def test_creator_plugin_package(self):
        sys.path.insert(0, str(REPO / "tools"))
        import make_pyz

        out = temp_dir(self)
        pyz = make_pyz.make_pyz(out / "autobiz-plugin.pyz")
        package = make_pyz.make_creator_plugin(pyz, out / "creator.zip")
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("autobiz-plugin-creator/plugin.json"))
        self.assertEqual(names, sorted(names))
        self.assertIn("autobiz-plugin-creator/skills/autobiz-plugin-creator/scripts/autobiz-plugin.pyz", names)
        self.assertIn("autobiz-plugin-creator/skills/autobiz-plugin-skeleton/SKILL.md", names)
        self.assertEqual(manifest["skills"], "./skills/")


if __name__ == "__main__":
    unittest.main()
