#!/usr/bin/env python3
"""把脚手架打成一个文件 autobiz-plugin.pyz（标准库 zipapp，D57）。

包内：scaffold/ 包（含模块包的 files/），以及 scaffold/_data/ 下的 runtime/、schemas/ 和 new 的种子
（examples/lite、examples/fullstack 的核心配置，显式列出，Q12.1）。执行方式：python3 autobiz-plugin.pyz <命令>。

用法：python3 tools/make_pyz.py [-o dist/autobiz-plugin.pyz]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIPPED = ("__pycache__", ".DS_Store", "Thumbs.db")
SEED_FILES = {
    "lite": ("plugin.scaffold.json", "workflow.json", "modules/board.json", "modules/session.json",
             "modules/knowledge.json", "modules/artifactSync.json"),
    "fullstack": ("plugin.scaffold.json", "workflow.json", "modules/board.json", "modules/session.json",
                  "modules/knowledge.json", "modules/artifactSync.json", ".mcp.json", "hooks/hooks.json"),
}
MAIN = "import sys\n\nfrom scaffold.cli import main\n\nsys.exit(main())\n"


def _copy_tree(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if any(part in SKIPPED for part in rel.parts) or path.suffix == ".pyc" or not path.is_file():
            continue
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)


def stage(directory: Path) -> None:
    _copy_tree(REPO / "scaffold", directory / "scaffold")
    data = directory / "scaffold" / "_data"
    _copy_tree(REPO / "runtime", data / "runtime")
    _copy_tree(REPO / "schemas", data / "schemas")
    for name, files in SEED_FILES.items():
        for rel in files:
            destination = data / "examples" / name / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / "examples" / name / rel, destination)
    (directory / "__main__.py").write_text(MAIN, encoding="utf-8")


def make_pyz(output: Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autobiz-pyz-") as temporary:
        staging = Path(temporary) / "app"
        stage(staging)
        zipapp.create_archive(staging, output, interpreter="/usr/bin/env python3", compressed=True)
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="打包 autobiz-plugin.pyz")
    parser.add_argument("-o", "--output", default=str(REPO / "dist" / "autobiz-plugin.pyz"))
    args = parser.parse_args(argv)
    path = make_pyz(Path(args.output))
    print(f"已生成 {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
