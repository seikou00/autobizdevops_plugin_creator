"""new：以问答或 --answers 生成核心配置，再执行 doctor（interfaces.md §1.4，D56）。

交互模式先选择全引导或自行配置；加 --yes 时不提问，回答取自 --answers。
--skeleton 只写出带 [TODO: …] 占位的核心配置骨架，不执行 doctor，由开发者填完后再 doctor、package（D63）。
--manual 默认同时生成全部公开模块的配置骨架和一个空白 SKILL.md。
"""

from __future__ import annotations

from pathlib import Path

from scaffold import resources
from scaffold.build.load import PUBLIC_MODULE_KEYS
from scaffold.commands import CommandResult
from scaffold.commands.doctor import doctor
from scaffold.commands.edit import import_agents, import_skill
from scaffold.lib import derive, fsio, jsonedit, skillmd
from scaffold.lib.issues import UsageError
from scaffold.lib.tree import Tree

PLUGIN_FIELDS = ("id", "name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def schema_ref(rel: str) -> str:
    if rel == "plugin.scaffold.json":
        return "./.scaffold/plugin-scaffold.schema.json"
    if rel.startswith("modules/"):
        return f"../.scaffold/modules/{Path(rel).name.replace('.json', '.schema.json')}"
    return "./.scaffold/workflow.schema.json"


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


def apply_answers(answers: dict) -> tuple:
    """把回答写成核心配置，返回 (files, 要导入的技能)（interfaces.md §1.4）。"""
    files = {}
    entry = {"$schema": schema_ref("plugin.scaffold.json"), "scaffoldVersion": 1, "plugin": {}}
    if isinstance(answers.get("plugin"), dict):
        entry["plugin"] = {key: answers["plugin"][key] for key in PLUGIN_FIELDS + ("mcpServers", "hooks")
                           if key in answers["plugin"]}
        for field in ("id", "name"):
            value = entry["plugin"].get(field)
            if isinstance(value, str):
                entry["plugin"][field] = derive.prefixed_plugin_field(value)
    if answers.get("globalHooks") is not None:
        raise UsageError("新建插件暂不支持 globalHooks")
    if "nodes" in answers:
        if not isinstance(answers["nodes"], list) or not answers["nodes"]:
            raise UsageError("--answers 的 nodes 必须是非空数组")
        files["workflow.json"] = dump_config(workflow_from(answers["nodes"]))
    for key in PUBLIC_MODULE_KEYS:
        if key not in answers or answers[key] is None:
            continue
        rel = f"modules/{key}.json"
        files[rel] = dump_config({"$schema": schema_ref(rel), **answers[key]})
        entry.setdefault("modules", {})[key] = f"./{rel}"
    files["plugin.scaffold.json"] = dump_config(entry)
    skills = answers.get("skills") or {}
    if not isinstance(skills, dict):
        raise UsageError("--answers 的 skills 必须是对象：技能名 → 导入目录或 null")
    return files, skills


def interactive(target: Path, prompter) -> dict:
    """问答得到回答；在内存中先 lint，有 error 时报出并重新回答，回答被放弃时什么都不写（interfaces.md §1.4）。"""
    from scaffold import wizard
    from scaffold.build.pipeline import analyze
    from scaffold.lib.issues import Report

    while True:
        answers = wizard.ask(prompter)
        files, _ = apply_answers(answers)
        errors = [issue for issue in analyze(Tree(target, files), stale=False).report.issues if issue.level == "error"]
        if not errors:
            return answers
        prompter.say(Report(errors).to_text())
        if not wizard.yes(prompter, "配置有问题，重新回答？", True):
            raise UsageError("已放弃，没有写入任何文件")


def new(target: Path, *, answers: dict | None = None, yes: bool = False, prompter=None) -> CommandResult:
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise UsageError(f"目标目录 {target} 必须不存在或为空")
    if not yes:
        from scaffold import wizard

        if answers is not None:
            raise UsageError("--answers 要与 --yes 一起使用")
        prompter = prompter or wizard.TerminalPrompter()
        try:
            manual = wizard.ask_manual_configuration(prompter)
            if not manual:
                answers = interactive(target, prompter)
        except (EOFError, KeyboardInterrupt):
            raise UsageError("问答被中断，没有写入任何文件") from None
        if manual:
            return skeleton(target, [], with_skill=True)
    if answers is None or "nodes" not in answers or "plugin" not in answers:
        raise UsageError("--yes 时 --answers 必须给出 plugin 和 nodes")
    files, skills = apply_answers(answers)
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
                  "source": {"type": "git", "url": "[TODO: 知识仓库 HTTPS 地址；知识随插件打包或由 DevClaw 提供时，删掉整个 source]",
                             "ref": "master"}},
    "artifactSync": {"allowedFrom": "[TODO: 从哪个节点完成起允许同步，写成 <节点 id>:done]",
                     "artifacts": {"[TODO: 要上传的产物路径，与 workflow.json 中的 outputs 一致]": "[TODO: 简述]"}},
}


def skeleton_files(modules: list, *, with_skill: bool = False) -> dict:
    """生成配置骨架、Schema 和可选的空白节点技能。"""
    from scaffold.build.framework import SCHEMA_FILES

    entry = {"$schema": schema_ref("plugin.scaffold.json"), "scaffoldVersion": 1,
             "plugin": {"id": f"{derive.PLUGIN_PREFIX}[TODO: 插件 ID 后缀，仅英文字母、数字、短横线和下划线]",
                        "name": f"{derive.PLUGIN_PREFIX}[TODO: 插件名后缀]",
                        "version": "0.1.0", "description": "[TODO: 一句话描述]"},
             "workflow": "./workflow.json"}
    referenced_modules = modules
    if with_skill and not modules:
        modules = list(PUBLIC_MODULE_KEYS)
        referenced_modules = [key for key in modules if key != "artifactSync"]
    if referenced_modules:
        entry["modules"] = {key: f"./modules/{key}.json" for key in referenced_modules}
    files = {"plugin.scaffold.json": dump_config(entry)}
    first_node = skeleton_node(1)
    nodes = {"biz": [first_node]}
    if with_skill:
        skill = "my-skill"
        first_node["skill"] = skill
        files[f"skills/{skill}/SKILL.md"] = (
            f'---\nname: {skill}\ndescription: "{skillmd.TODO_DESCRIPTION}"\n---\n\n'.encode("utf-8")
        )
    else:
        nodes["dev"] = [skeleton_node(2)]
    files["workflow.json"] = dump_config({"$schema": schema_ref("workflow.json"), "nodes": nodes})
    for key in modules:
        rel = f"modules/{key}.json"
        files[rel] = dump_config({"$schema": schema_ref(rel), **SKELETON_MODULES[key]})
    for name in SCHEMA_FILES:
        files[f".scaffold/{name}"] = resources.read_bytes(f"schemas/{name}")
    return files


def skeleton(target: Path, modules: list, *, with_skill: bool = False) -> CommandResult:
    from scaffold.lib.issues import Report

    unknown = [key for key in modules if key not in PUBLIC_MODULE_KEYS]
    if unknown:
        raise UsageError(f"没有模块 {'、'.join(unknown)}，可选：{'、'.join(PUBLIC_MODULE_KEYS)}")
    modules = [key for key in PUBLIC_MODULE_KEYS if key in modules]
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise UsageError(f"目标目录 {target} 必须不存在或为空")
    files = skeleton_files(modules, with_skill=with_skill)
    for rel, data in sorted(files.items()):
        fsio.atomic_write(target / rel, data)
    (target / "hooks").mkdir(exist_ok=True)
    written = sorted(files)
    source_files = [rel for rel in written if not rel.startswith(".scaffold/")]
    heading = "已写出配置骨架和空白技能" if with_skill else "已写出核心配置骨架"
    fill_skill = (
        " 填写 SKILL.md 的 description 和正文。改技能名时，同步改目录名、name 和节点的 skill。"
        if with_skill else ""
    )
    remove_modules = (
        "  先删除不需要的模块配置，同时删掉 plugin.scaffold.json 的 modules 中对应的引用。\n"
        if with_skill else ""
    )
    if with_skill and not modules:
        remove_modules += (
            '  产物同步默认关闭。要启用时，填好 modules/artifactSync.json，'
            '再向 modules 添加 "artifactSync": "./modules/artifactSync.json"。\n'
        )
    text = "\n".join([
        f"{heading}：" + "、".join(source_files),
        "下一步：\n" + remove_modules
        + "  1. 填写核心配置和已引用模块中的 [TODO: …]，按需增删 workflow.json 中的节点。" + fill_skill,
        f"  2. autobiz-plugin -C {target} lint      # 逐项列出还没填的字段",
        f"  3. autobiz-plugin -C {target} doctor    # 生成插件（还有没填的字段时不生成）",
        f"  4. autobiz-plugin -C {target} package   # 打包",
    ])
    return CommandResult(Report(), written=written, text=text)
