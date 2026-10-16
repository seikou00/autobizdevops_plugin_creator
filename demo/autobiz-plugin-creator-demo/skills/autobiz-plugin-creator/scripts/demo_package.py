#!/usr/bin/env python3
"""演示版 package：把 build 好的插件打成可以导入 DevClaw 的 zip。

包含 plugin.json、.codex-plugin/、board_core/、runtime/、skills/、hooks/、agents/ 和清单引用的 .mcp.json；
不包含核心配置（plugin.scaffold.json、workflow.json、modules/）、.scaffold/ 和 __pycache__。
zip 内的根目录名为插件 ID，输出到 <插件目录>/dist/<插件 ID>-<版本>.zip。

用法：python3 demo_package.py <插件目录>
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path

INCLUDED = ("plugin.json", ".codex-plugin", "board_core", "runtime", "skills", "hooks", "agents")
SKIPPED = {"__pycache__", ".DS_Store"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="打包 build 好的插件")
    parser.add_argument("plugin_dir", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.plugin_dir).expanduser().resolve()
    if not (root / "runtime" / "build-manifest.json").is_file():
        print(f"用法错误：{root} 还没有 build", file=sys.stderr)
        return 2
    manifest = json.loads((root / "runtime" / "build-manifest.json").read_text(encoding="utf-8"))
    version = json.loads((root / "plugin.json").read_text(encoding="utf-8"))["version"]
    plugin_id = manifest["pluginId"]
    output = root / "dist" / f"{plugin_id}-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    entries = list(INCLUDED)
    mcp = json.loads((root / "plugin.json").read_text(encoding="utf-8")).get("mcpServers")
    if mcp:
        entries.append(mcp[2:] if mcp.startswith("./") else mcp)
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            source = root / entry
            paths = [source] if source.is_file() else sorted(source.rglob("*")) if source.is_dir() else []
            for path in paths:
                if SKIPPED.intersection(path.parts) or path.suffix == ".pyc":
                    continue
                archive.write(path, f"{plugin_id}/{path.relative_to(root).as_posix()}")
                count += path.is_file()
    print(f"已打包 {count} 个文件：{output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
