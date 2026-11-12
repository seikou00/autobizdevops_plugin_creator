"""开发者可以手改的文字字段（D70）：plugin.json、board_core/board_config.json、runtime/config/board.json 中的
对话提示和展示文案。

改过的文字在 doctor、package 时保留，文件的其余部分照常按核心配置重写；改动超出文字字段时 check 报漂移。
"""

import json
import unittest
import zipfile

from scaffold.build import customize
from scaffold.lib import fsio
from tests.helpers import cli, new_from_example

BOARD = "runtime/config/board.json"
CONFIG = "board_core/board_config.json"
RUNTIME = "runtime/config/runtime.json"
MANIFEST = "runtime/build-manifest.json"
RELEASE_ID = "AutoBizDevOps_doc-review"
TODO = "[TODO: 做什么；在什么情况下使用]"
TIP = "nodes.biz[draft].nextAction.not_started.dialogTips"


def codes(payload, level=None):
    return sorted({issue["code"] for issue in payload["issues"] if level is None or issue["level"] == level})


def records(root):
    return json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))["files"]


def load(root, rel):
    return json.loads((root / rel).read_text("utf-8"))


def save(root, rel, value, indent=2):
    (root / rel).write_text(json.dumps(value, ensure_ascii=False, indent=indent) + "\n", "utf-8")


class CustomizedTextTest(unittest.TestCase):
    def plugin(self):
        root = new_from_example(self, "minimal")
        for path in (root / "skills").rglob("SKILL.md"):
            path.write_text(path.read_text("utf-8").replace(TODO, "起草或评审文档时使用"), "utf-8")
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        return root

    def customize(self, root):
        plugin = load(root, "plugin.json")
        plugin["description"] = "资深开发者改过的描述"
        save(root, "plugin.json", plugin, indent=4)
        board = load(root, BOARD)
        board["nodes"]["biz"][0]["nextAction"]["not_started"]["dialogTips"] = "先写一版草稿。"
        board["stateLabels"]["in_progress"] = "处理中"
        save(root, BOARD, board)
        config = load(root, CONFIG)
        config["inspectCommands"]["darwin"]["system_prompt_inject"] = "只在 FEATURE_DIR 中写产物。"
        save(root, CONFIG, config)

    def test_text_edits_survive_doctor_and_package(self):
        root = self.plugin()
        self.customize(root)
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 0, payload)
        self.assertNotIn("DRIFT_GENERATED", codes(payload))
        self.assertTrue(payload["contract"]["ran"])

        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["changes"]["customized"], {
            CONFIG: ["inspectCommands.darwin.system_prompt_inject"], "plugin.json": ["description"],
            BOARD: [TIP, "stateLabels.in_progress"]})
        self.assertEqual(codes(payload, "warning"), [])
        files = records(root)
        self.assertEqual(sorted(files[BOARD]["customized"]), [TIP, "stateLabels.in_progress"])
        self.assertIn(TIP, files[BOARD]["texts"])
        self.assertNotIn("customized", files["runtime/config/flow.json"])

        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 0, payload)
        with zipfile.ZipFile(root / payload["package"]["path"]) as archive:
            packed = json.loads(archive.read(f"{RELEASE_ID}/plugin.json"))
            board = json.loads(archive.read(f"{RELEASE_ID}/{BOARD}"))
            config = json.loads(archive.read(f"{RELEASE_ID}/{CONFIG}"))
        self.assertEqual((packed["version"], packed["description"]), ("0.1.1", "资深开发者改过的描述"))
        self.assertEqual(board["nodes"]["biz"][0]["nextAction"]["not_started"]["dialogTips"], "先写一版草稿。")
        self.assertEqual(board["stateLabels"]["in_progress"], "处理中")
        self.assertEqual(config["inspectCommands"]["darwin"]["system_prompt_inject"], "只在 FEATURE_DIR 中写产物。")
        self.assertNotEqual(config["inspectCommands"]["linux"]["system_prompt_inject"], "只在 FEATURE_DIR 中写产物。")

        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["written"], [])
        self.assertEqual(cli("-C", str(root), "check")[0], 0)

    def test_package_prefixes_edited_name_and_legacy_id_with_or_without_bump(self):
        root = self.plugin()
        plugin = load(root, "plugin.json")
        manifest = load(root, MANIFEST)
        record = manifest["files"]["plugin.json"]
        record["structure"] = customize.structure("plugin.json", plugin, exclude=("name",))
        del record["texts"]["name"]
        save(root, MANIFEST, manifest)
        plugin["name"] = "手改名称"
        save(root, "plugin.json", plugin)

        for bump, version in (("none", "0.1.0"), ("patch", "0.1.1")):
            with self.subTest(bump=bump):
                code, payload = cli("-C", str(root), "package", "--bump", bump)
                self.assertEqual(code, 0, payload)
                path = payload["package"]["path"]
                self.assertEqual(path, f"dist/{RELEASE_ID}-{version}.zip")
                with zipfile.ZipFile(root / path) as archive:
                    packed = archive.read(f"{RELEASE_ID}/plugin.json")
                    runtime = archive.read(f"{RELEASE_ID}/{RUNTIME}")
                    manifest = json.loads(archive.read(f"{RELEASE_ID}/{MANIFEST}"))
                self.assertEqual(json.loads(packed)["name"], "AutoBizDevOps_手改名称")
                self.assertEqual(json.loads(packed)["version"], version)
                self.assertEqual(json.loads(runtime)["pluginId"], RELEASE_ID)
                self.assertEqual(manifest["pluginId"], RELEASE_ID)
                self.assertEqual(manifest["files"]["plugin.json"]["sha256"], fsio.digest(packed))
                self.assertEqual(manifest["files"][RUNTIME]["sha256"], fsio.digest(runtime))
                self.assertEqual(load(root, "plugin.json")["name"], "手改名称")
                self.assertEqual(load(root, RUNTIME)["pluginId"], "doc-review")

    def test_core_changes_still_flow_into_the_file(self):
        root = self.plugin()
        self.customize(root)
        workflow = load(root, "workflow.json")
        workflow["nodes"]["biz"][1]["name"] = "审阅"
        workflow["nodes"]["biz"].append({"id": "publish", "seq": 3, "name": "发布", "skill": "doc-publish",
                                         "outputs": ["PUBLISH.md"]})
        save(root, "workflow.json", workflow)
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        board = load(root, BOARD)
        draft, review, publish = board["nodes"]["biz"]
        self.assertEqual(draft["nextAction"]["not_started"]["dialogTips"], "先写一版草稿。")       # 改过的文字保留
        self.assertEqual(board["stateLabels"]["in_progress"], "处理中")
        self.assertIn("审阅", review["nextAction"]["in_progress"]["dialogTips"])                 # 没改的文字跟随改名
        self.assertEqual(publish["id"], "publish")                                              # 新节点照常生成
        self.assertEqual(draft["nextAction"]["done"]["dialogTips"], "下一阶段：审阅。")
        commands = load(root, CONFIG)["inspectCommands"]["darwin"]
        self.assertEqual(commands["system_prompt_inject"], "只在 FEATURE_DIR 中写产物。")
        self.assertIn("审阅", commands["dialog_tips"])                                          # 节点链跟随改名
        self.assertEqual(load(root, "plugin.json")["description"], "资深开发者改过的描述")

    def test_conflicting_text_is_kept_with_warning(self):
        root = self.plugin()
        config = load(root, CONFIG)
        config["inspectCommands"]["darwin"]["dialog_tips"] = "请描述本次要写的文档。"
        save(root, CONFIG, config)
        workflow = load(root, "workflow.json")
        workflow["nodes"]["biz"][1]["name"] = "审阅"               # 默认的 dialog_tips 含节点链，这次生成的值也变了
        save(root, "workflow.json", workflow)
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertEqual(codes(payload, "warning"), ["CUSTOMIZED_STALE"])
        self.assertEqual(load(root, CONFIG)["inspectCommands"]["darwin"]["dialog_tips"], "请描述本次要写的文档。")

    def test_edits_outside_text_fields(self):
        root = self.plugin()
        config = load(root, CONFIG)
        generated = config["inspectCommands"]["darwin"]["project_status"]
        config["inspectCommands"]["darwin"]["project_status"] = "echo hacked"
        config["inspectCommands"]["darwin"]["dialog_tips"] = "请描述本次要写的文档。"
        save(root, CONFIG, config)
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT_GENERATED", codes(payload, "error"))
        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 1)

        code, payload = cli("-C", str(root), "doctor")           # 文字以外的改动按核心配置重写，文字保留
        self.assertEqual(code, 0, payload)
        self.assertEqual(codes(payload, "warning"), ["DRIFT_GENERATED"])
        commands = load(root, CONFIG)["inspectCommands"]["darwin"]
        self.assertEqual(commands["project_status"], generated)
        self.assertEqual(commands["dialog_tips"], "请描述本次要写的文档。")
        self.assertEqual(cli("-C", str(root), "check")[0], 0)

        plugin = load(root, "plugin.json")
        plugin["version"] = "9.9.9"
        save(root, "plugin.json", plugin)
        code, payload = cli("-C", str(root), "check")
        self.assertIn("DRIFT_GENERATED", codes(payload, "error"))

    def test_invalid_json_deletion_and_placeholders(self):
        root = self.plugin()
        (root / BOARD).write_text("{ broken", "utf-8")
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 1)
        self.assertIn("CUSTOMIZED_INVALID", codes(payload, "error"))
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("CUSTOMIZED_INVALID", codes(payload, "error"))

        (root / BOARD).unlink()                                 # 删掉即恢复生成内容
        code, payload = cli("-C", str(root), "doctor")
        self.assertEqual(code, 0, payload)
        self.assertNotIn("customized", records(root)[BOARD])

        board = load(root, BOARD)
        board["template"]["description"] = "[TODO: 流程说明]"
        save(root, BOARD, board)
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 0, payload)
        self.assertIn("TODO_PLACEHOLDER", codes(payload, "warning"))
        code, payload = cli("-C", str(root), "package")
        self.assertEqual(code, 1)
        self.assertIn("TODO_PLACEHOLDER", codes(payload, "error"))

    def test_other_generated_files_stay_protected(self):
        root = self.plugin()
        flow = root / "runtime/config/flow.json"
        flow.write_text(flow.read_text("utf-8").replace("起草进行中", "起草处理中"), "utf-8")
        code, payload = cli("-C", str(root), "check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT_GENERATED", codes(payload, "error"))


if __name__ == "__main__":
    unittest.main()
