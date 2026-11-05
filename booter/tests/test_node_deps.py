"""知识模块在 doctor 时安装 collector 的 Node 依赖，失败报 KNOWLEDGE_NODE_DEPS（README §9 第 7 条）。

用一个假的 npm（放在 PATH 最前面）代替真实的 npm install，测试不联网。
"""

import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from scaffold.commands.package import collect
from tests.helpers import REPO, copy_example, temp_dir

FAKE_OK = """#!/bin/sh
mkdir -p node_modules/gray-matter
echo '{"name": "gray-matter"}' > node_modules/gray-matter/package.json
echo 'module.exports = {}' > node_modules/gray-matter/index.js
"""
FAKE_FAIL = """#!/bin/sh
echo 'npm error code ENOTFOUND' >&2
echo 'npm error network request to https://registry.npmjs.org/gray-matter failed' >&2
exit 1
"""


@unittest.skipIf(sys.platform == "win32", "假的 npm 是 shell 脚本")
class NodeDepsTest(unittest.TestCase):
    def run_cli(self, root, *args, npm=None):
        env = {key: value for key, value in os.environ.items() if key != "AUTOBIZ_SKIP_NPM_INSTALL"}
        env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        bin_dir = temp_dir(self)
        if npm is not None:
            script = bin_dir / "npm"
            script.write_text(npm, "utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        # 只留系统目录，确保找不到真实的 npm
        env["PATH"] = os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"])
        completed = subprocess.run([sys.executable, "-m", "scaffold", "-C", str(root), *args, "--json"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(REPO), env=env)
        return completed.returncode, json.loads(completed.stdout.decode("utf-8"))

    def codes(self, payload):
        return [issue["code"] for issue in payload["issues"]]

    def test_doctor_installs_and_package_ships_node_modules(self):
        root = copy_example(self, "lite", temp_dir(self) / "plugin")
        code, payload = self.run_cli(root, "doctor", npm=FAKE_OK)
        self.assertEqual(code, 0, payload)
        self.assertNotIn("KNOWLEDGE_NODE_DEPS", self.codes(payload))
        self.assertTrue((root / "runtime/knowledge/node_modules/gray-matter/package.json").is_file())
        manifest = json.loads((root / "runtime/build-manifest.json").read_text("utf-8"))
        self.assertIn("runtime/knowledge/package.json", manifest["files"])
        self.assertFalse(any("node_modules" in path for path in manifest["files"]))
        # 示例的技能还有 TODO 占位，package 会拒绝；直接按打包清单收集文件
        entry = json.loads((root / "plugin.scaffold.json").read_text("utf-8"))
        files, skipped = collect(root, entry, manifest, knowledge_enabled=True, knowledge_source=True)
        self.assertIn("runtime/knowledge/node_modules/gray-matter/index.js", files)
        self.assertIn("runtime/knowledge/package.json", files)
        self.assertFalse(any("node_modules" in path for path in skipped))
        code, payload = self.run_cli(root, "check", npm=FAKE_OK)
        self.assertNotIn("KNOWLEDGE_NODE_DEPS", self.codes(payload))

    def test_doctor_warns_when_install_fails(self):
        root = copy_example(self, "lite", temp_dir(self) / "plugin")
        code, payload = self.run_cli(root, "doctor", npm=FAKE_FAIL)
        self.assertEqual(code, 0, payload)
        issue = next(issue for issue in payload["issues"] if issue["code"] == "KNOWLEDGE_NODE_DEPS")
        self.assertEqual(issue["level"], "warning")
        self.assertIn("gray-matter", issue["message"])
        self.assertIn("ENOTFOUND", issue["message"])
        self.assertIn("npm install", issue["hint"])
        # check 只提醒，不安装
        code, payload = self.run_cli(root, "check", npm=FAKE_OK)
        self.assertIn("KNOWLEDGE_NODE_DEPS", self.codes(payload))
        self.assertFalse((root / "runtime/knowledge/node_modules").exists())

    def test_doctor_warns_without_npm(self):
        root = copy_example(self, "lite", temp_dir(self) / "plugin")
        code, payload = self.run_cli(root, "doctor")
        self.assertEqual(code, 0, payload)
        issue = next(issue for issue in payload["issues"] if issue["code"] == "KNOWLEDGE_NODE_DEPS")
        self.assertIn("找不到 npm", issue["message"])

    def test_no_install_without_plugin_assembler(self):
        root = copy_example(self, "minimal", temp_dir(self) / "plugin")
        code, payload = self.run_cli(root, "doctor", npm=FAKE_FAIL)
        self.assertEqual(code, 0, payload)
        self.assertNotIn("KNOWLEDGE_NODE_DEPS", self.codes(payload))


if __name__ == "__main__":
    unittest.main()
