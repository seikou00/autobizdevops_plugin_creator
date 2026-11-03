"""以参考插件为基线的金样测试（README §3.1）：示例生成的插件在命令中输出的看板数据，与 lite、全栈版现有
board_config.json 中对应的内容比较。参考仓库与本仓库并列存放（与 autobizdevops_plugin_creator 同级的
autobizdevops_lite、autobiz_kanban），不在时跳过。

比较的内容：节点顺序、id（去掉阶段前缀，D36）、label、group、skill、checkpoints、order、states 的状态与名称、
输出产物的路径、类型和必需性、runtimePolicy、主干 checkpoint 流转与标签、模板名称和描述。

已知且有意的差异（input-config.md §9.2 与下列决策）：
- 全栈版：order 按排列后的位置计算（D38），checkpoint 标签按节点名推导（D34），needs_fix 回流预留到 v2（README §7），
  `.jsonl` 按扩展名推断为 file（input-config.md §2.3），模板描述去掉了动态节点的说明（D32）；
- 两者：节点描述、nextAction 文案、产物 id 与显示名、输入、validators 不再沿用（D33、D39、§9.2）。
"""

import json
import subprocess
import sys
import unittest

from tests.helpers import SIBLINGS, built_example, temp_dir

REFERENCES = {"lite": SIBLINGS / "autobizdevops_lite", "fullstack": SIBLINGS / "autobiz_kanban"}
KNOWN = {
    "lite": {"order": False, "labels": False, "types": {}, "template_description": True},
    "fullstack": {"order": True, "labels": True, "types": {"evidence/EVIDENCE.jsonl": ("file", "json")},
                  "template_description": False},
}
V2_CHECKPOINTS = ("needs_fix",)


def command(plugin, script, *args):
    completed = subprocess.run([sys.executable, "-X", "utf8", str(plugin / script), *args], stdout=subprocess.PIPE)
    return json.loads(completed.stdout.decode("utf-8"))


class ReferenceTest(unittest.TestCase):
    maxDiff = None

    def compare(self, name):
        reference = REFERENCES[name] / "board_core" / "board_config.json"
        if not reference.is_file():
            self.skipTest(f"没有参考仓库 {REFERENCES[name].name}")
        theirs = json.loads(reference.read_text("utf-8"))["workflow"]
        known = KNOWN[name]
        plugin = built_example(self, name)
        workspace = temp_dir(self)
        (workspace / "p").mkdir()
        mine = command(plugin, "runtime/adapters/inspect_state.py", "--mode", "project", "--workspace", str(workspace),
                       "--projects", "p")["workflow"]["nodes"]
        templates = command(plugin, "runtime/adapters/inspect_workflow_templates.py")
        self.assertEqual([node["id"] for node in mine], [node["id"].split(".", 1)[-1] for node in theirs["nodes"]])
        for ours, other in zip(mine, theirs["nodes"]):
            for key in ("label", "group", "skill", "checkpoints") + (() if known["order"] else ("order",)):
                self.assertEqual(ours[key], other[key], f"{name}/{ours['id']}.{key}")
            self.assertEqual([(state["nodeStatus"], state["label"]) for state in ours["states"]],
                             [(state["nodeStatus"], state["label"]) for state in other["states"]], ours["id"])
            expected = [(item["path"], known["types"][item["path"]][0] if item["path"] in known["types"]
                         else item["artifactType"], item.get("required", True)) for item in other["artifacts"]["outputs"]]
            self.assertEqual([(item["path"], item["artifactType"], item["required"]) for item in ours["artifacts"]["outputs"]],
                             expected, f"{name}/{ours['id']} 的输出")
            self.assertEqual(ours.get("runtimePolicy"), other.get("runtimePolicy"), f"{name}/{ours['id']}.runtimePolicy")
        ours_cp, theirs_cp = templates["checkpoints"], theirs["checkpoints"]
        self.assertEqual(ours_cp["initial"][0], theirs_cp["initial"][0])
        expected_transitions = {checkpoint: [item for item in following if item not in V2_CHECKPOINTS]
                                for checkpoint, following in theirs_cp["transitions"].items()
                                if checkpoint not in V2_CHECKPOINTS}
        self.assertEqual(ours_cp["transitions"], expected_transitions)
        if not known["labels"]:
            self.assertEqual(ours_cp["stageLabels"], theirs_cp["stageLabels"])
        standard = theirs["templates"]["standard"]
        self.assertEqual(templates["templates"][0]["label"], standard["label"])
        if known["template_description"]:
            self.assertEqual(templates["templates"][0]["description"], standard["description"])

    def test_lite(self):
        self.compare("lite")

    def test_fullstack(self):
        self.compare("fullstack")


if __name__ == "__main__":
    unittest.main()
