"""产物检查钩子与 hooks/hooks.json（D61）：脚手架维护自己的条目，开发者的条目写在同一个文件、原样保留。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import cli, temp_dir

GUARD = "python -X utf8 hooks/artifact_guard.py"
MINE = {"matcher": "write_file", "hooks": [{"type": "command", "command": "python hooks/mine.py"}]}
STOP = {"hooks": [{"type": "command", "command": "python hooks/stop.py"}]}


def commands(hooks: dict) -> list:
    hooks = hooks.get("hooks", hooks)
    return [(event, hook["command"]) for event, items in hooks.items() for item in items for hook in item["hooks"]]


class HooksTest(unittest.TestCase):
    def new_lite(self) -> Path:
        root = temp_dir(self) / "plugin"
        code, payload = cli("new", str(root), "--from", "lite", "--yes")
        self.assertEqual(code, 0, payload)
        return root

    def read(self, root: Path) -> dict:
        return json.loads((root / "hooks/hooks.json").read_text("utf-8"))

    def write(self, root: Path, value) -> None:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        (root / "hooks/hooks.json").write_text(text, "utf-8")

    def test_guard_is_written_to_root_hooks_dir(self):
        root = self.new_lite()
        self.assertEqual(json.loads((root / "plugin.json").read_text("utf-8"))["hooks"], "./hooks/hooks.json")
        self.assertEqual(commands(self.read(root)), [("PreToolUse", GUARD)])
        self.assertTrue((root / "hooks/artifact_guard.py").is_file())
        self.assertFalse((root / "runtime/hooks").exists())
        manifest = json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["files"]["hooks/hooks.json"]["ownership"], "seeded")
        self.assertEqual(manifest["files"]["hooks/artifact_guard.py"]["ownership"], "managed")

    def test_developer_entries_in_the_same_file_are_kept(self):
        root = self.new_lite()
        hooks = self.read(root)
        hooks["PreToolUse"].append(MINE)
        hooks["Stop"] = [STOP]
        self.write(root, hooks)

        # 开发者的条目直接生效，不需要重新生成
        code, payload = cli("-C", str(root), "check")
        self.assertNotIn("BUILD_STALE", [issue["code"] for issue in payload["issues"]])
        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertEqual(commands(self.read(root)),
                         [("PreToolUse", GUARD), ("PreToolUse", "python hooks/mine.py"), ("Stop", "python hooks/stop.py")])

    def test_removed_or_edited_guard_entry_is_restored_in_front(self):
        root = self.new_lite()
        self.write(root, {"PreToolUse": [MINE]})

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertEqual(commands(self.read(root)), [("PreToolUse", GUARD), ("PreToolUse", "python hooks/mine.py")])

    def test_wrapped_file_keeps_the_wrapper(self):
        root = self.new_lite()
        self.write(root, {"hooks": {"Stop": [STOP]}})

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        hooks = self.read(root)
        self.assertEqual(list(hooks), ["hooks"])
        self.assertEqual(commands(hooks), [("PreToolUse", GUARD), ("Stop", "python hooks/stop.py")])

    def test_plugin_hooks_must_point_to_the_shared_file(self):
        root = self.new_lite()
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        entry["plugin"]["hooks"] = "./hooks/custom.json"
        (root / "plugin.scaffold.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")

        code, payload = cli("-C", str(root), "lint")

        self.assertEqual(code, 1, payload)
        self.assertIn("PLUGIN_HOOKS_PATH", [issue["code"] for issue in payload["issues"]])

    def test_invalid_hooks_file_is_rejected(self):
        root = self.new_lite()
        self.write(root, '{"PreToolUse": {"matcher": "execute"}}')

        code, payload = cli("-C", str(root), "lint")

        self.assertEqual(code, 1, payload)
        self.assertIn("PLUGIN_HOOKS_INVALID", [issue["code"] for issue in payload["issues"]])


if __name__ == "__main__":
    unittest.main()
