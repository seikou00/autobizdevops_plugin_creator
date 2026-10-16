#!/usr/bin/env python3
"""列出或导入技能资源（对应正式版的 autobiz-plugin add skill --from）。

    python3 demo_skills.py list <插件目录> [--from <技能来源目录>]
    python3 demo_skills.py import <插件目录> --from <技能目录> [--name <技能名>]

list 列出插件 skills/ 下和来源目录中已有的技能（name、description、是否有模板和脚本），供建模时绑定节点。
import 把一个技能目录原样复制到 <插件目录>/skills/<技能名>/，目标已存在时拒绝覆盖。
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
IGNORED = shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc")


def frontmatter(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    keys = {}
    for line in (match.group(1).splitlines() if match else []):
        found = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if found:
            keys[found.group(1)] = found.group(2).strip().strip("'\"")
    return keys


def describe(directory):
    keys = frontmatter(directory / "SKILL.md")
    return {"dir": directory.name, "path": str(directory), "name": keys.get("name", ""),
            "description": keys.get("description", ""),
            "templates": sorted(p.relative_to(directory).as_posix() for p in (directory / "templates").rglob("*")
                                if p.is_file()) if (directory / "templates").is_dir() else [],
            "scripts": sorted(p.relative_to(directory).as_posix() for p in (directory / "scripts").rglob("*")
                              if p.is_file()) if (directory / "scripts").is_dir() else []}


def find_skills(base):
    if (base / "SKILL.md").is_file():
        return [describe(base)]
    if (base / "skills").is_dir():
        base = base / "skills"
    return [describe(path) for path in sorted(base.iterdir()) if (path / "SKILL.md").is_file()] if base.is_dir() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description="列出或导入技能资源")
    parser.add_argument("action", choices=["list", "import"])
    parser.add_argument("plugin_dir")
    parser.add_argument("--from", dest="source", help="技能来源：单个技能目录，或包含多个技能的目录")
    parser.add_argument("--name", help="导入后的技能名，默认取 frontmatter 中的 name，再退回目录名")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    plugin = Path(args.plugin_dir).expanduser().resolve()
    if args.action == "list":
        result = {"plugin": find_skills(plugin / "skills") if (plugin / "skills").is_dir() else []}
        if args.source:
            result["source"] = find_skills(Path(args.source).expanduser().resolve())
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        for where, skills in (("插件 skills/", result["plugin"]), ("来源目录", result.get("source"))):
            if skills is None:
                continue
            print(f"{where}：{len(skills)} 个技能")
            for skill in skills:
                mismatch = "" if skill["name"] == skill["dir"] else f"（frontmatter name 是 {skill['name'] or '空'}）"
                print(f"  {skill['dir']}{mismatch}：{skill['description'] or '没有 description'}")
                if skill["templates"]:
                    print(f"    模板：{'、'.join(skill['templates'])}")
                if skill["scripts"]:
                    print(f"    脚本：{'、'.join(skill['scripts'])}")
        return 0
    if not args.source:
        print("用法错误：import 需要 --from <技能目录>", file=sys.stderr)
        return 2
    source = Path(args.source).expanduser().resolve()
    if not (source / "SKILL.md").is_file():
        print(f"用法错误：{source} 下没有 SKILL.md", file=sys.stderr)
        return 2
    name = args.name or frontmatter(source / "SKILL.md").get("name") or source.name
    if not SKILL_NAME.match(name) or len(name) > 64:
        print(f"技能名 {name} 不合法：只能用小写字母和数字，用 - 连接，不超过 64 字符；用 --name 指定", file=sys.stderr)
        return 1
    target = plugin / "skills" / name
    if target.exists():
        print(f"skills/{name} 已存在，不会覆盖", file=sys.stderr)
        return 1
    shutil.copytree(source, target, ignore=IGNORED)
    print(f"已导入：{source} → skills/{name}/")
    if frontmatter(target / "SKILL.md").get("name") != name:
        print(f"注意：SKILL.md 中的 name 与技能名 {name} 不一致，build 会报 SKILL_NAME_MISMATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
