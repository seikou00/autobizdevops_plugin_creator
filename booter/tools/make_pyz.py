#!/usr/bin/env python3
"""发布脚手架：打出单文件的 autobiz-plugin.pyz（标准库 zipapp，D57）。

.pyz 包内：scaffold/ 包（含模块包的 files/），以及 scaffold/_data/ 下的 runtime/、schemas/。
执行方式：python3 autobiz-plugin.pyz <命令>。

booter 目录本身也能直接运行（python3 <booter 目录> <命令>，D69），booter 根目录的 SKILL.md 就这样调用 CLI，
不需要 .pyz；.pyz 只用于把 CLI 单独拷给别人。

用法（在 booter/ 下）：python3 tools/make_pyz.py [-o dist/autobiz-plugin.pyz]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # booter/
SKIPPED = ("__pycache__", ".DS_Store", "Thumbs.db")
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
