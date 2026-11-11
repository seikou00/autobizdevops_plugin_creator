"""声明 knowledge.source 时，doctor 写盘后把知识仓库拉到 sys/，契约测试不再报 KNOWLEDGE_MANIFEST_MISSING。

用本地 git 仓库作为 source，测试不联网。
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import REPO, copy_example, temp_dir

MANIFEST = {"schemaVersion": "v1",
            "systems": [{"systemId": "demo", "systemName": "示例系统", "agentsPath": "demo/AGENTS.md",
                         "deployUnits": [{"deployUnitId": "demo-web", "name": "前端"}]}]}


@unittest.skipIf(shutil.which("git") is None, "需要 git")
class KnowledgePullTest(unittest.TestCase):
    def run_cli(self, root, *args):
        env = {key: value for key, value in os.environ.items() if key != "AUTOBIZ_SKIP_KNOWLEDGE_PULL"}
        env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1", GIT_TERMINAL_PROMPT="0")
        completed = subprocess.run([sys.executable, "-m", "scaffold", "-C", str(root), *args, "--json"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(REPO), env=env)
        return completed.returncode, json.loads(completed.stdout.decode("utf-8"))

    def codes(self, payload):
        return [issue["code"] for issue in payload["issues"]]

    def knowledge_repo(self):
        repo = temp_dir(self) / "knowledge"
        (repo / "demo").mkdir(parents=True)
        (repo / "agents.manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False), "utf-8")
        (repo / "demo" / "AGENTS.md").write_text("# demo\n", "utf-8")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        for args in (["init", "-q", "-b", "master"], ["add", "."], ["commit", "-q", "-m", "init"]):
            subprocess.run(git + args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return repo

    def plugin(self, url):
        root = copy_example(self, "lite", temp_dir(self) / "plugin")
        config = root / "modules" / "knowledge.json"
        data = json.loads(config.read_text("utf-8"))
        data["source"] = {"type": "git", "url": str(url), "ref": "master"}
        config.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return root

    def test_doctor_pulls_knowledge_for_contract_test(self):
        root = self.plugin(self.knowledge_repo())
        code, payload = self.run_cli(root, "doctor")
        self.assertEqual(code, 0, payload)
        self.assertNotIn("KNOWLEDGE_PULL", self.codes(payload))
        self.assertTrue((root / "sys" / "agents.manifest.json").is_file())
        _, payload = self.run_cli(root, "check")
        self.assertNotIn("KNOWLEDGE_MANIFEST_MISSING", self.codes(payload))

    def test_existing_manifest_is_not_pulled_again(self):
        root = self.plugin(temp_dir(self) / "missing")
        (root / "sys").mkdir()
        (root / "sys" / "agents.manifest.json").write_text(json.dumps(MANIFEST), "utf-8")
        code, payload = self.run_cli(root, "doctor")
        self.assertEqual(code, 0, payload)
        self.assertNotIn("KNOWLEDGE_PULL", self.codes(payload))

    def test_pull_failure_is_warning(self):
        root = self.plugin(temp_dir(self) / "missing")
        code, payload = self.run_cli(root, "doctor")
        self.assertEqual(code, 0, payload)
        issues = [issue for issue in payload["issues"] if issue["code"] == "KNOWLEDGE_PULL"]
        self.assertEqual([issue["level"] for issue in issues], ["warning"], payload)
        self.assertFalse((root / "sys").exists())
        _, payload = self.run_cli(root, "check")
        self.assertIn("KNOWLEDGE_MANIFEST_MISSING", self.codes(payload))


if __name__ == "__main__":
    unittest.main()
