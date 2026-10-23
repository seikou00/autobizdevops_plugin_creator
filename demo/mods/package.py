#!/usr/bin/env python3
"""把 demo/mods/ 下的每个 mod 打包成可以导入 DevClaw 的 zip。

    python3 demo/mods/package.py

输出到 demo/dist/<名称>-<版本>.zip，zip 内的顶层目录就是 mod 的目录名。
测试、引擎生成的类型声明和 tsconfig.json 不打包。
"""

import json
import zipfile
from pathlib import Path

MODS = Path(__file__).resolve().parent
DIST = MODS.parent / "dist"
SKIPPED_PARTS = {"__pycache__", ".DS_Store", "tests"}
SKIPPED_PATHS = {".claude-plugin/types", "tsconfig.json"}


def is_skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if SKIPPED_PARTS.intersection(path.relative_to(root).parts):
        return True
    return any(rel == p or rel.startswith(p + "/") for p in SKIPPED_PATHS)


def package(mod: Path) -> Path:
    manifest = json.loads((mod / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    output = DIST / f"{manifest['name']}-{manifest['version']}.zip"
    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(mod.rglob("*")):
            if path.is_file() and not is_skipped(path, mod):
                archive.write(path, path.relative_to(MODS).as_posix())
    return output


def main():
    for mod in sorted(p for p in MODS.iterdir() if (p / ".claude-plugin" / "plugin.json").is_file()):
        print(f"已打包：{package(mod).relative_to(MODS.parent.parent)}")


if __name__ == "__main__":
    main()
