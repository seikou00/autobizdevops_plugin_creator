"""new：以种子、问答或 --answers 为起点生成核心配置，再执行 doctor（interfaces.md §1.4，D56）。

不加 --yes 时进入初始化向导（scaffold/wizard.py）；加 --yes 时不提问，回答取自 --from 的种子和 --answers。
--skeleton 只写出带 [TODO: …] 占位的核心配置骨架，不执行 doctor，由开发者填完后再 doctor、package（D63）。
"""

from __future__ import annotations

import re
from pathlib import Path

from scaffold import resources
from scaffold.build.load import MODULE_KEYS
from scaffold.commands import CommandResult
from scaffold.commands.doctor import doctor
from scaffold.commands.edit import import_agents, import_skill
from scaffold.lib import derive, fsio, jsonedit
from scaffold.lib.issues import UsageError
from scaffold.lib.tree import Tree

TEMPLATES = ("blank", "lite", "fullstack")
SCHEMA_REF = re.compile(r'("\$schema"\s*:\s*")[^"]*(")')
PLUGIN_FIELDS = ("id", "name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def schema_ref(rel: str) -> str:
    if rel == "plugin.scaffold.json":
        return "./.scaffold/plugin-scaffold.schema.json"
    if rel.startswith("modules/"):
        return f"../.scaffold/modules/{Path(rel).name.replace('.json', '.schema.json')}"
    return "./.scaffold/workflow.schema.json"


def rewrite_schema(rel: str, data: bytes) -> bytes:
    text = fsio.decode(data)
    return SCHEMA_REF.sub(lambda match: match.group(1) + schema_ref(rel) + match.group(2), text, count=1).encode("utf-8")


def seed_files(template: str) -> dict:
    """种子：入口文件、workflow.json、入口引用的模块配置，以及清单透传引用的文件（Q12.1）。"""
    if template == "blank":
        return {}
    base = f"examples/{template}"
    entry = fsio.parse_json(resources.read_bytes(f"{base}/plugin.scaffold.json"))
    files = {"plugin.scaffold.json": resources.read_bytes(f"{base}/plugin.scaffold.json")}
    references = [entry.get("workflow", "./workflow.json")] + list((entry.get("modules") or {}).values())
    for ref in references:
        rel = ref[2:] if ref.startswith("./") else ref
        files[rel] = resources.read_bytes(f"{base}/{rel}")
    seeded = {rel: rewrite_schema(rel, data) for rel, data in files.items()}
    for key in ("mcpServers", "hooks"):
        ref = entry.get("plugin", {}).get(key)
        if ref:
            rel = ref[2:] if ref.startswith("./") else ref
            if resources.exists(f"{base}/{rel}"):
                seeded[rel] = resources.read_bytes(f"{base}/{rel}")
    return seeded


def dump_config(value: dict) -> bytes:
    """按示例的手排格式写核心配置：对象逐个键换行，只含标量的数组写在一行。"""
    return (jsonedit.render(value, "", "  ", "\n") + "\n").encode("utf-8")


def load_answers(source: str | None) -> dict | None:
    if source is None:
        return None
    import sys

    try:
        data = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
        answers = fsio.parse_json(data, source)
    except OSError as error:
        raise UsageError(f"无法读取 --answers {source}: {error}") from None
    except fsio.JsonError as error:
        raise UsageError(f"--answers 不是合法的 JSON：{error.describe()}") from None
    if not isinstance(answers, dict):
        raise UsageError("--answers 必须是 JSON 对象")
    return answers


def workflow_from(nodes: list) -> dict:
    groups = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or node.get("stage") not in derive.GROUPS:
            raise UsageError(f"--answers 的 nodes[{index}] 缺少 stage（biz、dev 或 ops）")
        item = {key: node[key] for key in ("id", "seq", "name", "skill", "outputs", "terminal") if key in node}
        groups.setdefault(node["stage"], []).append(item)
    return {"$schema": "./.scaffold/workflow.schema.json",
            "nodes": {group: groups[group] for group in derive.GROUPS if group in groups}}


def apply_answers(files: dict, answers: dict, template: str) -> tuple:
    """返回 (files, 要导入的技能)；写了的类别整体替换种子中的对应内容（interfaces.md §1.4）。"""
    entry = fsio.parse_json(files["plugin.scaffold.json"]) if "plugin.scaffold.json" in files else {
        "$schema": "./.scaffold/plugin-scaffold.schema.json", "scaffoldVersion": 1, "plugin": {}}
    changed = False
    if isinstance(answers.get("plugin"), dict):
        entry["plugin"] = {**entry.get("plugin", {}), **answers["plugin"]}
        entry["plugin"] = {key: entry["plugin"][key] for key in PLUGIN_FIELDS + ("mcpServers", "hooks")
                           if key in entry["plugin"]}
        changed = True
    if "nodes" in answers:
        if not isinstance(answers["nodes"], list) or not answers["nodes"]:
            raise UsageError("--answers 的 nodes 必须是非空数组")
        workflow_rel = (entry.get("workflow") or "./workflow.json")[2:]
        files[workflow_rel] = dump_config(workflow_from(answers["nodes"]))
    for key in MODULE_KEYS:
        if key not in answers or answers[key] is None:
            continue
        rel = f"modules/{key}.json"
        files[rel] = dump_config({"$schema": schema_ref(rel), **answers[key]})
        entry.setdefault("modules", {})[key] = f"./{rel}"
        changed = True
    if changed or "plugin.scaffold.json" not in files:
        files["plugin.scaffold.json"] = dump_config(entry)
    skills = answers.get("skills") or {}
    if not isinstance(skills, dict):
        raise UsageError("--answers 的 skills 必须是对象：技能名 → 导入目录或 null")
    return files, skills


def interactive(target: Path, template: str, prompter) -> dict:
    """问答得到回答；在内存中先 lint，有 error 时报出并重新回答，回答被放弃时什么都不写（interfaces.md §1.4）。"""
    from scaffold import wizard
    from scaffold.build.pipeline import analyze
    from scaffold.lib.issues import Report

    seed = seed_files(template)
    seed_plugin = fsio.parse_json(seed["plugin.scaffold.json"]).get("plugin", {}) if seed else {}
    while True:
        answers = wizard.ask(prompter, seed_plugin=seed_plugin, seeded=template != "blank")
        files, _ = apply_answers(dict(seed), answers, template)
        errors = [issue for issue in analyze(Tree(target, files), stale=False).report.issues if issue.level == "error"]
        if not errors:
            return answers
        prompter.say(Report(errors).to_text())
        if not wizard.yes(prompter, "配置有问题，重新回答？", True):
            raise UsageError("已放弃，没有写入任何文件")


def new(target: Path, *, template: str = "blank", answers: dict | None = None, yes: bool = False,
        prompter=None) -> CommandResult:
    if template not in TEMPLATES:
        raise UsageError(f"--from 只能是 {'、'.join(TEMPLATES)}")
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise UsageError(f"目标目录 {target} 必须不存在或为空")
    if not yes:
        from scaffold.wizard import TerminalPrompter

        if answers is not None:
            raise UsageError("--answers 要与 --yes 一起使用")
        try:
            answers = interactive(target, template, prompter or TerminalPrompter())
        except (EOFError, KeyboardInterrupt):
            raise UsageError("问答被中断，没有写入任何文件") from None
    files = seed_files(template)
    skills = {}
    if answers is not None:
        files, skills = apply_answers(files, answers, template)
    if template == "blank" and (answers is None or "nodes" not in answers or "plugin" not in answers):
        raise UsageError("--from blank 时 --answers 必须给出 plugin 和 nodes")
    tree = Tree(target, files)
    bound = {node.get("skill") for node in (answers or {}).get("nodes", []) if isinstance(node, dict)}
    issues = []
    for skill, source in skills.items():
        overlay, found, _ = import_skill(tree, skill, Path(source) if source else None, bound=skill in bound)
        if source:
            files.update(overlay)
            tree = Tree(target, files)
        issues += found
    agents = (answers or {}).get("agents")
    if agents is not None:
        if not isinstance(agents, str):
            raise UsageError("--answers 的 agents 必须是 agents 目录的路径")
        files.update(import_agents(tree, Path(agents)))
    result = doctor(target, overlay=files, extra_issues=issues)
    if not result.report.failed():
        (target / "hooks").mkdir(parents=True, exist_ok=True)
    return result


# —— new --skeleton ——

def skeleton_node(seq: int) -> dict:
    return {"id": "[TODO: 节点 id，小写字母开头，只含小写字母、数字和 _]", "seq": seq,
            "name": "[TODO: 看板上显示的节点名]", "skill": "[TODO: 技能目录名，小写字母、数字和连字符]",
            "outputs": ["[TODO: 节点产出的文件名；没有产出就删掉 outputs]"]}


SKELETON_MODULES = {
    "board": {"display": {"workflowLabel": "[TODO: 看板上的流程名称]"}},
    "session": {"policies": {"default": {"agentMode": "multi"}}},
    "knowledge": {"assembly": {"assembler": "plugin"},
                  "source": {"type": "git", "url": "[TODO: 知识仓库 HTTPS 地址；插件不拉取知识仓库就删掉 source]",
                             "ref": "main"}},
    "artifactSync": {"allowedFrom": "[TODO: 从哪个节点完成起允许同步，写成 <节点 id>:done]",
                     "artifacts": {"[TODO: 要上传的产物路径，与 workflow.json 中的 outputs 一致]": "[TODO: 简述]"}},
    "globalHooks": {"hooks": ["[TODO: 全局钩子 id，见 autobiz-plugin hook list]"]},
}


def skeleton_files(modules: list) -> dict:
    """入口文件、workflow.json、所选模块的配置骨架，以及 IDE 补全用的 .scaffold/ Schema。"""
    from scaffold.build.framework import SCHEMA_FILES

    entry = {"$schema": schema_ref("plugin.scaffold.json"), "scaffoldVersion": 1,
             "plugin": {"id": "[TODO: 插件 id，小写字母、数字和连字符，发布后不能改]", "name": "[TODO: 插件名]",
                        "version": "0.1.0", "description": "[TODO: 一句话描述]"},
             "workflow": "./workflow.json"}
    if modules:
        entry["modules"] = {key: f"./modules/{key}.json" for key in modules}
    workflow = {"$schema": schema_ref("workflow.json"),
                "nodes": {"biz": [skeleton_node(1)], "dev": [skeleton_node(2)]}}
    files = {"plugin.scaffold.json": dump_config(entry), "workflow.json": dump_config(workflow)}
    for key in modules:
        rel = f"modules/{key}.json"
        files[rel] = dump_config({"$schema": schema_ref(rel), **SKELETON_MODULES[key]})
    for name in SCHEMA_FILES:
        files[f".scaffold/{name}"] = resources.read_bytes(f"schemas/{name}")
    return files


def skeleton(target: Path, modules: list) -> CommandResult:
    from scaffold.lib.issues import Report

    unknown = [key for key in modules if key not in MODULE_KEYS]
    if unknown:
        raise UsageError(f"没有模块 {'、'.join(unknown)}，可选：{'、'.join(MODULE_KEYS)}")
    modules = [key for key in MODULE_KEYS if key in modules]
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise UsageError(f"目标目录 {target} 必须不存在或为空")
    files = skeleton_files(modules)
    for rel, data in sorted(files.items()):
        fsio.atomic_write(target / rel, data)
    (target / "hooks").mkdir(exist_ok=True)
    written = sorted(files)
    configs = [rel for rel in written if not rel.startswith(".scaffold/")]
    text = "\n".join([
        "已写出核心配置骨架：" + "、".join(configs),
        "下一步：",
        "  1. 把各文件中的 [TODO: …] 按说明填好（workflow.json 中的节点按需增删，ops 组可以自己加）；",
        f"  2. autobiz-plugin -C {target} lint      # 逐项列出还没填的字段",
        f"  3. autobiz-plugin -C {target} doctor    # 生成插件（还有没填的字段时不生成）",
        f"  4. autobiz-plugin -C {target} package   # 打包",
    ])
    return CommandResult(Report(), written=written, text=text)
