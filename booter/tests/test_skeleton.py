"""new --skeleton（D63）：写出带 [TODO: …] 占位的核心配置骨架，lint 逐项提示，填完才能 doctor。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import cli, temp_dir


def todo_fields(payload) -> dict:
    return {(issue["file"], issue["pointer"]): issue["level"]
            for issue in payload["issues"] if issue["code"] == "TODO_FIELD"}


def edit(root: Path, rel: str, change) -> None:
    path = root / rel
    data = json.loads(path.read_text("utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def fill(root: Path) -> None:
    edit(root, "plugin.scaffold.json", lambda d: d["plugin"].update(id="my-plugin", name="我的插件", description="示例"))

    def nodes(d):
        d["nodes"]["biz"][0].update(id="prd", name="需求", skill="my-prd", outputs=["PRD.md"])
        d["nodes"]["dev"][0].update(id="code", name="编码", skill="my-code")
        d["nodes"]["dev"][0].pop("outputs")
    edit(root, "workflow.json", nodes)


class SkeletonTest(unittest.TestCase):
    def skeleton(self, *modules) -> Path:
        root = temp_dir(self) / "plugin"
        args = ["new", str(root), "--skeleton"]
        for module in modules:
            args += ["--module", module]
        code, payload = cli(*args)
        self.assertEqual(code, 0, payload)
        return root

    def test_writes_only_core_config_with_placeholders(self):
        root = self.skeleton("board", "globalHooks")

        files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                       if path.is_file() and ".scaffold" not in path.parts)
        self.assertEqual(files, ["modules/board.json", "modules/globalHooks.json", "plugin.scaffold.json",
                                 "workflow.json"])
        self.assertTrue((root / ".scaffold/workflow.schema.json").is_file())
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        self.assertEqual(entry["modules"], {"board": "./modules/board.json", "globalHooks": "./modules/globalHooks.json"})
        self.assertIn("[TODO:", entry["plugin"]["id"])
        workflow = json.loads((root / "workflow.json").read_text("utf-8"))
        self.assertEqual(list(workflow["nodes"]), ["biz", "dev"])
        self.assertEqual(list(workflow["nodes"]["biz"][0]), ["id", "seq", "name", "skill", "outputs"])

    def test_lint_lists_every_unfilled_field_and_doctor_writes_nothing(self):
        root = self.skeleton("artifactSync")
        before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

        code, payload = cli("-C", str(root), "lint")

        self.assertEqual(code, 1, payload)
        found = todo_fields(payload)
        for pointer in ("/plugin/id", "/plugin/name", "/plugin/description"):
            self.assertEqual(found[("plugin.scaffold.json", pointer)], "error")
        for group in ("biz", "dev"):
            for field in ("id", "name", "skill", "outputs/0"):
                self.assertEqual(found[("workflow.json", f"/nodes/{group}/0/{field}")], "error")
        self.assertEqual(found[("modules/artifactSync.json", "/allowedFrom")], "error")
        self.assertNotIn("INPUT_SCHEMA", [issue["code"] for issue in payload["issues"]])

        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 1, payload)
        self.assertEqual(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")), before)

    def test_filled_skeleton_builds(self):
        root = self.skeleton()
        fill(root)

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertTrue((root / "plugin.json").is_file())
        self.assertTrue((root / "skills/autobiz/my-prd/SKILL.md").is_file())
        self.assertNotIn("TODO_FIELD", [issue["code"] for issue in payload["issues"]])

    def test_artifact_descriptions_may_stay_until_package(self):
        root = self.skeleton("artifactSync")
        fill(root)
        edit(root, "modules/artifactSync.json", lambda d: d.update(allowedFrom="prd:done", artifacts={"PRD.md": "[TODO: 简述]"}))

        code, payload = cli("-C", str(root), "doctor")

        self.assertEqual(code, 0, payload)
        self.assertEqual(todo_fields(payload), {("modules/artifactSync.json", "/artifacts/PRD.md"): "warning"})
        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 1, payload)
        self.assertIn("TODO_PLACEHOLDER", [issue["code"] for issue in payload["issues"] if issue["level"] == "error"])

    def test_usage_errors(self):
        target = temp_dir(self) / "plugin"
        self.assertEqual(cli("new", str(target), "--skeleton", "--from", "lite")[0], 2)
        self.assertEqual(cli("new", str(target), "--skeleton", "--module", "nope")[0], 2)
        self.assertEqual(cli("new", str(target), "--from", "lite", "--yes", "--module", "board")[0], 2)
        self.assertFalse(target.exists())
        root = self.skeleton()
        self.assertEqual(cli("new", str(root), "--skeleton")[0], 2)


if __name__ == "__main__":
    unittest.main()
