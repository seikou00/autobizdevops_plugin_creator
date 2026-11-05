"""金样测试：对示例执行 build，生成内容与示例的 output/ 逐字节一致（examples/README.md）。

minimal 在 booter/examples/，lite、fullstack 在仓库根目录的 fixtures/（不在时跳过）。

build-manifest 中内容固定的托管文件摘要写作 "…"，只比较归属。
"""

import json
import unittest

from tests.helpers import built_example, example_dir
from scaffold.build.pipeline import build
from scaffold.lib.tree import Tree

PLACEHOLDER = "…"


class ExamplesTest(unittest.TestCase):
    maxDiff = None

    def compare(self, name):
        root = built_example(self, name)
        expected_root = example_dir(self, name) / "output"
        for expected in sorted(path for path in expected_root.rglob("*") if path.is_file() and path.name != ".DS_Store"):
            rel = expected.relative_to(expected_root).as_posix()
            actual = root / rel
            self.assertTrue(actual.is_file(), f"{name}: 没有生成 {rel}")
            if rel == "runtime/build-manifest.json":
                self.compare_manifest(name, json.loads(expected.read_text("utf-8")), json.loads(actual.read_text("utf-8")))
            else:
                self.assertEqual(actual.read_bytes(), expected.read_bytes(), f"{name}: {rel} 与金样不一致")
        return root

    def compare_manifest(self, name, expected, actual):
        self.assertEqual({key: value for key, value in actual.items() if key != "files"},
                         {key: value for key, value in expected.items() if key != "files"}, name)
        self.assertEqual(list(actual["files"]), list(expected["files"]), f"{name}: build-manifest 的文件清单不一致")
        for path, record in expected["files"].items():
            if record.get("sha256") == PLACEHOLDER:
                self.assertEqual(actual["files"][path]["ownership"], record["ownership"], path)
            else:
                self.assertEqual(actual["files"][path], record, f"{name}: {path}")

    def test_minimal(self):
        self.compare("minimal")

    def test_lite(self):
        self.compare("lite")

    def test_fullstack(self):
        self.compare("fullstack")

    def test_rebuild_writes_nothing(self):
        root = built_example(self, "lite")
        self.assertEqual(build(Tree(root)).written, [])


if __name__ == "__main__":
    unittest.main()
