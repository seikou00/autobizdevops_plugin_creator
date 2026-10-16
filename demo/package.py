#!/usr/bin/env python3
"""同步演示技能的参考资料，并打包成 DevClaw 插件 zip。

    python3 demo/package.py              同步后打包到 demo/dist/
    python3 demo/package.py --sync-only  只同步 references/input-config.md 和 schemas/

技能自带的 references/input-config.md 和 schemas/ 是 docs/、schemas/ 的副本，
修改设计文档或 Schema 后需要重新同步。
"""

import argparse
import json
import shutil
import zipfile
from pathlib import Path

DEMO = Path(__file__).resolve().parent
REPO = DEMO.parent
PLUGIN = DEMO / "autobiz-plugin-creator-demo"
SKILL = PLUGIN / "skills" / "autobiz-plugin-creator"
SKIPPED = {"__pycache__", ".DS_Store"}


def sync():
    (SKILL / "references").mkdir(exist_ok=True)
    shutil.copyfile(REPO / "docs" / "input-config.md", SKILL / "references" / "input-config.md")
    target = SKILL / "schemas"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(REPO / "schemas", target)


def package():
    version = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))["version"]
    output = DEMO / "dist" / f"{PLUGIN.name}-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PLUGIN.rglob("*")):
            if not SKIPPED.intersection(path.parts):
                archive.write(path, path.relative_to(PLUGIN.parent).as_posix())
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sync-only", action="store_true", help="只同步参考资料，不打包")
    args = parser.parse_args()
    sync()
    print(f"已同步：{SKILL.relative_to(REPO)}/references/input-config.md、schemas/")
    if not args.sync_only:
        print(f"已打包：{package().relative_to(REPO)}")


if __name__ == "__main__":
    main()
