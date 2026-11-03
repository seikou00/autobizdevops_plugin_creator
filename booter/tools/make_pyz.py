#!/usr/bin/env python3
"""发布脚手架：打出 autobiz-plugin.pyz（标准库 zipapp，D57），再组装插件开发技能的 DevClaw 插件包（D58）。

.pyz 包内：scaffold/ 包（含模块包的 files/），以及 scaffold/_data/ 下的 runtime/、schemas/ 和 new 的种子
（examples/lite、examples/fullstack 的核心配置，显式列出，Q12.1）。执行方式：python3 autobiz-plugin.pyz <命令>。

插件包 autobiz-plugin-creator-<版本>.zip 只有一个顶层目录 autobiz-plugin-creator/：生成的 plugin.json，
skills/autobiz-plugin-creator/ 下的 SKILL.md、references/，以及放进 scripts/ 的同一个 .pyz（不提交进仓库）。

用法（在 booter/ 下）：python3 tools/make_pyz.py [-o dist/autobiz-plugin.pyz] [--no-creator]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # booter/
SKIPPED = ("__pycache__", ".DS_Store", "Thumbs.db")
SEED_FILES = {
    "lite": ("plugin.scaffold.json", "workflow.json", "modules/board.json", "modules/session.json",
             "modules/knowledge.json", "modules/artifactSync.json"),
    "fullstack": ("plugin.scaffold.json", "workflow.json", "modules/board.json", "modules/session.json",
                  "modules/knowledge.json", "modules/artifactSync.json", ".mcp.json", "hooks/hooks.json"),
}
MAIN = "import sys\n\nfrom scaffold.cli import main\n\nsys.exit(main())\n"
CREATOR = "autobiz-plugin-creator"
CREATOR_FILES = ("SKILL.md", "references/modeling-guide.md")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


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


def scaffold_version() -> str:
    sys.path.insert(0, str(REPO))
    from scaffold import SCAFFOLD_VERSION

    return SCAFFOLD_VERSION


def make_creator_plugin(pyz: Path, output: Path) -> Path:
    """插件开发技能的 DevClaw 插件包，与 demo 的 autobiz-plugin-creator-demo 相同（Q14.4）。"""
    version = scaffold_version()
    manifest = {"name": CREATOR, "version": version,
                "description": "AutoBiz 看板插件开发助手：对话梳理流程，用 autobiz-plugin 生成、检查并打包插件。",
                "skills": "./skills/"}
    entries = {"plugin.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    for rel in CREATOR_FILES:
        entries[f"skills/{CREATOR}/{rel}"] = (REPO / "skills" / CREATOR / rel).read_bytes()
    entries[f"skills/{CREATOR}/scripts/autobiz-plugin.pyz"] = Path(pyz).read_bytes()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(entries):
            info = zipfile.ZipInfo(f"{CREATOR}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if rel.endswith(".pyz") else 0o644) << 16
            archive.writestr(info, entries[rel])
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="打包 autobiz-plugin.pyz 和插件开发技能的插件包")
    parser.add_argument("-o", "--output", default=str(REPO / "dist" / "autobiz-plugin.pyz"))
    parser.add_argument("--no-creator", action="store_true", help="只打 .pyz，不组装插件开发技能的插件包")
    args = parser.parse_args(argv)
    path = make_pyz(Path(args.output))
    print(f"已生成 {path}")
    if not args.no_creator:
        plugin = make_creator_plugin(path, path.parent / f"{CREATOR}-{scaffold_version()}.zip")
        print(f"已生成 {plugin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
