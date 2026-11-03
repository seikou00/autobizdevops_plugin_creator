"""测试共用：把示例的核心配置拷到临时目录并生成插件。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # booter/
SIBLINGS = REPO.parents[1]                          # 与本仓库并列存放参考插件仓库的目录
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scaffold.build.pipeline import build  # noqa: E402
from scaffold.lib.tree import Tree  # noqa: E402


def temp_dir(test) -> Path:
    path = Path(tempfile.mkdtemp(prefix="autobiz-test-"))
    test.addCleanup(shutil.rmtree, path, True)
    return path


def copy_example(name: str, target: Path) -> Path:
    shutil.copytree(REPO / "examples" / name, target, ignore=shutil.ignore_patterns("output"))
    return target


def built_example(test, name: str) -> Path:
    root = copy_example(name, temp_dir(test) / name)
    result = build(Tree(root))
    test.assertTrue(result.ok, [issue for issue in result.report.issues if issue.level == "error"])
    return root


def run_script(plugin: Path, script: str, *args, env=None, cwd=None):
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("PLUGIN_WORKSPACE", "PROJECT_DIR", "PROJECT_CODE", "FEATURE_ID", "SESSION_ID",
                                  "AUTOBIZ_BOARD_ENDPOINT")}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(env or {})
    completed = subprocess.run([sys.executable, "-X", "utf8", str(plugin / script), *args], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment, cwd=cwd)
    return completed.returncode, json.loads(completed.stdout.decode("utf-8")), completed.stderr.decode("utf-8")


def cli(*args, cwd=None):
    completed = subprocess.run([sys.executable, "-m", "scaffold", *args, "--json"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=str(cwd or REPO),
                               env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"})
    return completed.returncode, json.loads(completed.stdout.decode("utf-8"))
