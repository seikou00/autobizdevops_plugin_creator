"""new --skeleton（D63）：写出带 [TODO: …] 占位的核心配置骨架，lint 逐项提示，填完才能 doctor。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scaffold.lib import skillmd
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
    edit(root, "plugin.scaffold.json", lambda d: d["plugin"].update(id="AutoBizDevOps_my-plugin", name="AutoBizDevOps_我的插件", description="示例"))

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
        root = self.skeleton("board")

        files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                       if path.is_file() and ".scaffold" not in path.parts)
        self.assertEqual(files, ["modules/board.json", "plugin.scaffold.json", "workflow.json"])
        self.assertTrue((root / ".scaffold/workflow.schema.json").is_file())
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        self.assertEqual(entry["modules"], {"board": "./modules/board.json"})
        for field in ("id", "name"):
            self.assertTrue(entry["plugin"][field].startswith("AutoBizDevOps_[TODO:"))
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

    def test_manual_skeleton_can_be_filled_and_packaged(self):
        root = temp_dir(self) / "plugin"
        code, payload = cli("new", str(root), "--manual")
        self.assertEqual(code, 0, payload)
        modules = {key: f"./modules/{key}.json" for key in ("board", "session", "knowledge", "artifactSync")}
        source_files = [rel for rel in payload["written"] if not rel.startswith(".scaffold/")]
        self.assertEqual(source_files, sorted([ref[2:] for ref in modules.values()]
                                              + ["plugin.scaffold.json", "skills/my-skill/SKILL.md", "workflow.json"]))
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        artifact_sync = root / modules.pop("artifactSync")
        draft = artifact_sync.read_bytes()
        self.assertEqual(entry["modules"], modules)
        self.assertFalse((root / "plugin.json").exists())
        skill = root / "skills/my-skill/SKILL.md"
        frontmatter = skillmd.parse_frontmatter(skill.read_text("utf-8"))
        self.assertEqual(frontmatter.fields["name"], "my-skill")
        self.assertTrue(skillmd.is_placeholder(frontmatter.fields["description"]))
        self.assertFalse(skillmd.has_state(skill.read_text("utf-8")))

        for path in modules.values():
            (root / path).unlink()
        edit(root, "plugin.scaffold.json", lambda d: d.pop("modules"))
        edit(root, "plugin.scaffold.json", lambda d: d["plugin"].update(
            id="AutoBizDevOps_test", name="AutoBizDevOps_测试", description="审阅文档"))
        edit(root, "workflow.json", lambda d: d["nodes"]["biz"][0].update(
            id="review", name="评审", outputs=["REVIEW.md"]))
        body = "检查文档，记录发现并保存到 REVIEW.md。"
        skill.write_text(f"---\nname: my-skill\ndescription: 审阅文档时使用\n---\n\n{body}\n", "utf-8")
        for command in ("lint", "doctor", "package"):
            code, payload = cli("-C", str(root), command)
            self.assertEqual(code, 0, payload)
        self.assertEqual(artifact_sync.read_bytes(), draft)
        board_modules = json.loads((root / "board_core/modules.json").read_text("utf-8"))["modules"]
        self.assertEqual(board_modules["artifactSync"], {"enabled": False})
        built_skill = (root / "skills/autobiz/my-skill/SKILL.md").read_text("utf-8")
        self.assertTrue(skillmd.has_state(built_skill))
        self.assertIn(body, built_skill)

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
        self.assertEqual(cli("new", str(target), "--skeleton", "--yes")[0], 2)
        self.assertEqual(cli("new", str(target), "--skeleton", "--module", "nope")[0], 2)
        self.assertEqual(cli("new", str(target), "--manual", "--skeleton")[0], 2)
        self.assertEqual(cli("new", str(target), "--manual", "--yes")[0], 2)
        self.assertEqual(cli("new", str(target), "--yes", "--module", "board")[0], 2)
        self.assertFalse(target.exists())
        root = self.skeleton()
        self.assertEqual(cli("new", str(root), "--skeleton")[0], 2)
        self.assertEqual(cli("new", str(root), "--manual")[0], 2)


if __name__ == "__main__":
    unittest.main()
