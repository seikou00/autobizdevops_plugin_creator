"""插件全局钩子模块 globalHooks（D62）：钩子目录完整性、new 的回答、hook 命令、合并顺序和校验。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import cli, temp_dir
from scaffold import resources
from scaffold.modules.global_hooks.catalog import HOOK_DIR, catalog

GUARD = "python -X utf8 hooks/artifact_guard.py"
SECRETS = "python -X utf8 hooks/secrets-check/check_secrets.py"
PERFORMANCE = "python -X utf8 hooks/performance-check/performance_checker.py code_done"


def commands(root: Path) -> list:
    hooks = json.loads((root / "hooks/hooks.json").read_text("utf-8"))
    hooks = hooks.get("hooks", hooks)
    return [hook["command"] for items in hooks.values() for item in items for hook in item["hooks"]]


def entry_of(root: Path) -> dict:
    return json.loads((root / "plugin.scaffold.json").read_text("utf-8"))


class CatalogTest(unittest.TestCase):
    def test_ships_secrets_and_performance_checks(self):
        self.assertEqual(list(catalog()), ["performance-check", "secrets-check"])

    def test_every_hook_references_only_its_own_files(self):
        for hook_id, spec in catalog().items():
            self.assertTrue(spec.title and spec.description, hook_id)
            self.assertTrue(spec.entries, hook_id)
            text = json.dumps(spec.entries)
            for name in spec.files:
                self.assertIn(f"{HOOK_DIR}/{name}", text, f"{hook_id} 的 entries 没有用到 {name}")
                self.assertTrue(resources.exists(f"{spec.package}/files/{name}"))
            self.assertNotIn(HOOK_DIR, json.dumps(spec.rendered_entries()))


ANSWERS = {"plugin": {"id": "hooks-demo", "name": "全局钩子", "version": "0.1.0", "description": "d"},
           "nodes": [{"stage": "biz", "id": "prd", "seq": 1, "name": "需求", "skill": "demo-prd", "outputs": ["PRD.md"]},
                     {"stage": "dev", "id": "code", "seq": 2, "name": "编码", "skill": "demo-code"}]}


class GlobalHooksModuleTest(unittest.TestCase):
    def new(self, hooks=None) -> Path:
        root = temp_dir(self) / "plugin"
        answers = dict(ANSWERS)
        if hooks is not None:
            answers["globalHooks"] = {"hooks": hooks}
        path = temp_dir(self) / "answers.json"
        path.write_text(json.dumps(answers, ensure_ascii=False), "utf-8")
        code, payload = cli("new", str(root), "--yes", "--answers", str(path))
        self.assertEqual(code, 0, payload)
        return root

    def test_new_answers_enable_the_module_in_modules_dir(self):
        root = self.new(["secrets-check", "performance-check"])

        self.assertEqual(entry_of(root)["modules"]["globalHooks"], "./modules/globalHooks.json")
        self.assertNotIn("optionalHooks", entry_of(root))
        config = json.loads((root / "modules/globalHooks.json").read_text("utf-8"))
        self.assertEqual(config["hooks"], ["secrets-check", "performance-check"])
        self.assertEqual(commands(root), [GUARD, SECRETS, PERFORMANCE])
        manifest = json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["modules"]["globalHooks"], "1.0.0")
        self.assertEqual(manifest["files"]["hooks/secrets-check/check_secrets.py"]["ownership"], "module")
        modules = json.loads((root / "board_core/modules.json").read_text("utf-8"))
        self.assertTrue(modules["modules"]["globalHooks"]["enabled"])

    def test_without_the_module_only_the_guard_is_registered(self):
        root = self.new()
        self.assertEqual(commands(root), [GUARD])
        self.assertFalse((root / "modules/globalHooks.json").exists())
        self.assertFalse((root / "hooks/secrets-check").exists())

    def test_module_hooks_come_before_developer_hooks(self):
        root = self.new(["secrets-check"])
        (root / "hooks/hooks.json").write_text(json.dumps({"PreToolUse": [
            {"matcher": "execute", "hooks": [{"type": "command", "command": "python hooks/mine.py"}]}]}), "utf-8")
        entry = entry_of(root)
        entry["plugin"]["hooks"] = "./hooks/hooks.json"
        (root / "plugin.scaffold.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertEqual(commands(root), [GUARD, SECRETS, "python hooks/mine.py"])

    def test_hook_commands_edit_the_module_file(self):
        root = self.new()
        code, payload = cli("-C", str(root), "hook", "enable", "performance-check")
        self.assertEqual(code, 0, payload)
        self.assertEqual(json.loads((root / "modules/globalHooks.json").read_text("utf-8"))["hooks"],
                         ["performance-check"])
        self.assertEqual(entry_of(root)["modules"]["globalHooks"], "./modules/globalHooks.json")

        code, payload = cli("-C", str(root), "hook", "enable", "secrets-check")
        self.assertEqual(code, 0, payload)
        self.assertEqual(commands(root), [GUARD, PERFORMANCE, SECRETS])

        code, payload = cli("-C", str(root), "hook", "list")
        self.assertEqual({hook["id"]: hook["enabled"] for hook in payload["hooks"]},
                         {"performance-check": True, "secrets-check": True})

        cli("-C", str(root), "hook", "disable", "secrets-check")
        code, payload = cli("-C", str(root), "hook", "disable", "performance-check")
        self.assertEqual(code, 0, payload)
        # 去光后关闭模块：只去掉引用，配置文件保留，旧脚本标为 inactive
        self.assertNotIn("globalHooks", entry_of(root)["modules"])
        self.assertTrue((root / "modules/globalHooks.json").is_file())
        self.assertEqual(commands(root), [GUARD])
        manifest = json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))
        self.assertTrue(manifest["files"]["hooks/performance-check/performance_checker.py"]["inactive"])

        code, payload = cli("-C", str(root), "hook", "enable", "no-such-hook")
        self.assertEqual(code, 2, payload)

    def test_module_enable_works_like_other_modules(self):
        root = self.new()
        code, payload = cli("-C", str(root), "module", "enable", "globalHooks", "--set", 'hooks=["secrets-check"]')
        self.assertEqual(code, 0, payload)
        self.assertEqual(commands(root), [GUARD, SECRETS])

    def test_unknown_or_duplicate_hooks_are_rejected(self):
        root = self.new(["secrets-check"])
        (root / "modules/globalHooks.json").write_text(json.dumps({"hooks": ["secrets-check", "secrets-check", "nope"]}),
                                                       "utf-8")

        code, payload = cli("-C", str(root), "lint")

        self.assertEqual(code, 1, payload)
        found = {issue["code"] for issue in payload["issues"]}
        self.assertTrue({"GLOBAL_HOOK_DUP", "GLOBAL_HOOK_UNKNOWN"} <= found, found)


if __name__ == "__main__":
    unittest.main()
