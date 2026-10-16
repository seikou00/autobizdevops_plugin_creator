#!/usr/bin/env python3
"""不经过 DevClaw 彩排演示脚本（demo/README.md）：在临时目录中按顺序执行技能会调用的脚本。

    python3 demo/rehearse.py [--keep]

步骤：导入示例技能 → 写核心配置并检查 → 制造 INPUT_FORWARD 再改回 → 加 modules/board.json →
build → simulate（评审校验会拒绝桩产物）→ simulate --skip-validate → 打包。
任何一步的退出码与预期不符时停止，并以 1 退出。
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEMO = Path(__file__).resolve().parent
SCRIPTS = DEMO / "autobiz-plugin-creator-demo" / "skills" / "autobiz-plugin-creator" / "scripts"
SAMPLES = DEMO / "sample-skills"

ENTRY = {"$schema": "./.scaffold/plugin-scaffold.schema.json", "scaffoldVersion": 1,
         "plugin": {"id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审"}}
WORKFLOW = {"$schema": "./.scaffold/workflow.schema.json", "nodes": [
    {"id": "draft", "name": "起草", "skill": "doc-draft",
     "outputs": {"draft": "DRAFT.md"}, "templates": ["templates/DRAFT.md"]},
    {"id": "review", "name": "评审", "skill": "doc-review", "inputs": ["draft"], "outputs": {"review": "REVIEW.md"},
     "validate": "${python} ${skillPath}/scripts/check_review.py --feature-dir ${featureDir}"}]}
BOARD = {"$schema": "../.scaffold/modules/board.schema.json",
         "display": {"artifacts": {"draft": "文档草稿", "review": "评审意见"}},
         "capabilities": {"knowledgeSedimentation": {"enabled": True}}}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def step(title, script, *args, expect=0):
    print(f"\n━━ {title}\n$ {script} {' '.join(str(arg) for arg in args)}")
    completed = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(completed.stdout.decode("utf-8", errors="replace").rstrip())
    if completed.returncode != expect:
        raise SystemExit(f"\n彩排中止：{script} 退出码 {completed.returncode}，预期 {expect}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", action="store_true", help="保留临时目录")
    args = parser.parse_args()
    temp = Path(tempfile.mkdtemp(prefix="autobiz-rehearse-"))
    plugin = temp / "doc-review"
    try:
        plugin.mkdir()
        step("3. 盘点技能", "demo_skills.py", "list", plugin, "--from", SAMPLES)
        for skill in ("doc-draft", "doc-review"):
            step(f"3. 导入 {skill}", "demo_skills.py", "import", plugin, "--from", SAMPLES / skill)
        write(plugin / "plugin.scaffold.json", ENTRY)
        write(plugin / "workflow.json", WORKFLOW)
        step("4. 建模后检查", "demo_lint.py", plugin)
        broken = json.loads(json.dumps(WORKFLOW))
        broken["nodes"][0]["inputs"] = ["review"]
        write(plugin / "workflow.json", broken)
        step("5. 故意制造错误：起草读取评审意见", "demo_lint.py", plugin, expect=1)
        write(plugin / "workflow.json", WORKFLOW)
        write(plugin / "modules" / "board.json", BOARD)
        write(plugin / "plugin.scaffold.json", {**ENTRY, "modules": {"board": "./modules/board.json"}})
        step("6. 加入看板模块后检查并预览", "demo_lint.py", plugin, "--preview")
        step("7. 生成插件", "demo_build.py", plugin)
        print("\n── skills/doc-review/SKILL.md（前 40 行）")
        print("\n".join((plugin / "skills" / "doc-review" / "SKILL.md").read_text(encoding="utf-8").splitlines()[:40]))
        step("8. 模拟 DevClaw（评审校验拒绝桩产物）", "demo_simulate.py", plugin, expect=1)
        step("8. 跳过校验再模拟", "demo_simulate.py", plugin, "--skip-validate")
        step("9. 打包", "demo_package.py", plugin)
        print(f"\n彩排完成。插件目录：{plugin}")
    finally:
        if args.keep:
            print(f"已保留临时目录：{temp}")
        else:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    main()
