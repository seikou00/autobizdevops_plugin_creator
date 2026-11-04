"""初始化向导：按七类输入问答（interfaces.md §1.4，scaffold.md 单元 12）。

问答与写配置分开：ask() 只收集回答，返回与 --answers 相同结构的字典，由 commands/new.py 写成核心配置。
每个问题都可以直接回车取默认值；节点的 id、seq 和产物 id 冲突当场追问。
"""

from __future__ import annotations

import re
import sys
from typing import Protocol

from scaffold.lib import derive

PLUGIN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SKILL = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AGENT_MODES = ("solo", "multi", "agent_team", "workflow")
PLATFORMS = ("darwin", "linux", "win32")
YES = ("y", "yes", "是", "Y")


class Prompter(Protocol):
    def ask(self, question: str, *, default=None, choices=None) -> str: ...

    def say(self, text: str) -> None: ...


class TerminalPrompter:
    def __init__(self, stream=None):
        self.stream = stream or sys.stderr

    def say(self, text: str) -> None:
        self.stream.write(text + "\n")
        self.stream.flush()

    def ask(self, question: str, *, default=None, choices=None) -> str:
        hint = f" [{'/'.join(choices)}]" if choices else ""
        shown = f"（默认 {default}）" if default not in (None, "") else ""
        while True:
            self.stream.write(f"? {question}{hint}{shown} › ")
            self.stream.flush()
            line = sys.stdin.readline()
            if not line:
                raise EOFError("输入已结束")
            value = line.strip() or ("" if default is None else str(default))
            if choices and value not in choices:
                self.say(f"  请输入 {'、'.join(choices)} 之一")
                continue
            return value


class ScriptedPrompter:
    """测试用：按顺序回答；回答为 None 时取默认值。"""

    def __init__(self, answers):
        self.answers = list(answers)
        self.lines = []

    def say(self, text: str) -> None:
        self.lines.append(text)

    def ask(self, question: str, *, default=None, choices=None) -> str:
        if not self.answers:
            raise EOFError(f"没有准备回答：{question}")
        value = self.answers.pop(0)
        value = ("" if default is None else str(default)) if value is None else str(value)
        if choices and value not in choices:
            raise ValueError(f"{question} 的回答 {value} 不在 {choices} 中")
        return value


def normalize_id(text: str) -> str:
    """规范化插件 ID：英文字母、数字、短横线和下划线以外的字符改为 -，合并连续的 -，去掉首尾的 -（input-config.md §3.3）。"""
    return re.sub(r"-+", "-", re.sub(r"[^A-Za-z0-9_-]+", "-", text)).strip("-")


def yes(prompter: Prompter, question: str, default: bool) -> bool:
    return prompter.ask(question, default="Y" if default else "N", choices=("Y", "N", "y", "n")) in YES


def ask_plugin(prompter: Prompter, seed: dict) -> dict:
    prompter.say("── 1 插件基础信息 ──")
    while True:
        raw = prompter.ask("插件 ID（slug，发布后不可修改）", default=seed.get("id"))
        plugin_id = normalize_id(raw)
        if plugin_id and PLUGIN_ID.match(plugin_id) and len(plugin_id) <= 64:
            if plugin_id != raw:
                prompter.say(f"  已规范化为 {plugin_id}")
            break
        prompter.say("  插件 ID 只能含英文字母、数字、短横线和下划线，不超过 64 字符")
    name = prompter.ask("插件名", default=seed.get("name") or plugin_id)
    version = prompter.ask("版本", default=seed.get("version", "0.1.0"))
    description = prompter.ask("一句话描述", default=seed.get("description") or name)
    return {**seed, "id": plugin_id, "name": name, "version": version, "description": description}


def _outputs(text: str) -> list:
    return [item.strip() for item in text.replace("，", ",").split(",") if item.strip()]


def ask_nodes(prompter: Prompter, existing_skills: list) -> list:
    prompter.say("── 2 核心流程（workflow.json）──")
    nodes = []
    while True:
        prompter.say(f"  节点 {len(nodes) + 1}")
        ids = {node["id"] for node in nodes}
        while True:
            node_id = prompter.ask("节点 id（小写字母开头，只含小写字母、数字和 _）")
            if not derive.ID_PATTERN.match(node_id):
                prompter.say("  id 只能用小写字母开头，只含小写字母、数字和 _")
            elif node_id in ids:
                prompter.say(f"  节点 id {node_id} 已经用过了")
            else:
                break
        name = prompter.ask("显示名", default=node_id)
        stage = prompter.ask("所属阶段", default=nodes[-1]["stage"] if nodes else "biz", choices=derive.GROUPS)
        seqs = {node["seq"] for node in nodes}
        while True:
            raw = prompter.ask("编排顺序 seq", default=max(seqs, default=0) + 1)
            if not raw.isdigit() or int(raw) < 1:
                prompter.say("  seq 是正整数")
                continue
            seq = int(raw)
            later_stage = [node for node in nodes if derive.GROUPS.index(node["stage"]) < derive.GROUPS.index(stage)
                           and node["seq"] > seq]
            if seq in seqs:
                prompter.say(f"  seq {seq} 已经用过了")
            elif later_stage:
                prompter.say(f"  seq 要按 biz → dev → ops 递增：{later_stage[0]['id']} 的 seq 是 {later_stage[0]['seq']}")
            else:
                break
        if existing_skills:
            prompter.say("  已有技能：" + "、".join(existing_skills))
        used = {node["skill"] for node in nodes}
        while True:
            skill = prompter.ask("绑定技能（已有技能名或新技能名）", default=node_id.replace("_", "-"))
            if not SKILL.match(skill):
                prompter.say("  技能名只能用小写字母、数字和连字符")
            elif skill in used:
                prompter.say("  一个技能只能绑定一个节点")
            else:
                break
        artifact_ids = {derive.artifact_id(path): path for node in nodes for path in node.get("outputs", [])}
        while True:
            outputs = _outputs(prompter.ask("产出产物（文件名，逗号分隔，可以为空）", default=""))
            problem = ""
            for path in outputs:
                artifact = derive.artifact_id(path)
                if derive.unsafe_path(path):
                    problem = f"{path} {derive.unsafe_path(path)}"
                elif not derive.ID_PATTERN.match(artifact):
                    problem = f"从 {path} 推导出的产物 id 不合法，换个文件名"
                elif artifact in artifact_ids and artifact_ids[artifact] != path:
                    problem = f"{path} 与 {artifact_ids[artifact]} 推导出同一个产物 id {artifact}，换个文件名"
            if not problem:
                break
            prompter.say("  " + problem)
        node = {"id": node_id, "name": name, "stage": stage, "seq": seq, "skill": skill}
        if outputs:
            node["outputs"] = outputs
        nodes.append(node)
        if not yes(prompter, "继续添加节点？", True):
            break
    nodes.sort(key=lambda node: node["seq"])
    last = nodes[-1]
    if not last.get("outputs") and yes(prompter, f"最后一个节点 {last['id']} 没有产物，它是终态节点（只推进到 archived）吗？", False):
        last["terminal"] = True
    return nodes


def ask_skills(prompter: Prompter, nodes: list, existing_skills: list) -> dict:
    prompter.say("── 3 技能资源 ──")
    skills = {}
    for node in nodes:
        if node["skill"] in existing_skills:
            continue
        path = prompter.ask(f"{node['skill']}：已有技能目录的路径（留空则生成空白 SKILL.md）", default="")
        skills[node["skill"]] = path or None
    return skills


def ask_board(prompter: Prompter) -> dict | None:
    prompter.say("── 4 看板 ──")
    raw = prompter.ask("目标平台（逗号分隔）", default=",".join(PLATFORMS))
    platforms = [item for item in _outputs(raw) if item in PLATFORMS] or list(PLATFORMS)
    return None if platforms == list(PLATFORMS) else {"target": {"platforms": platforms}}


def ask_session(prompter: Prompter, nodes: list) -> dict | None:
    prompter.say("── 5 会话与 Agent ──")
    mode = prompter.ask("默认运行策略", default="multi", choices=AGENT_MODES)
    policies = {}
    if mode != "multi":
        policies["default"] = {"agentMode": mode}
    if yes(prompter, "为节点单独配置策略？", False):
        groups = {}
        for node in nodes:
            node_mode = prompter.ask(f"{node['id']} 的运行策略", default=mode, choices=AGENT_MODES)
            if node_mode != mode:
                groups.setdefault(node["stage"], []).append({"id": node["id"], "agentMode": node_mode})
        if groups:
            policies["nodes"] = groups
    return {"policies": policies} if policies else None


def ask_modules(prompter: Prompter, nodes: list) -> tuple:
    prompter.say("── 6 知识与产物同步 ──")
    knowledge = artifact_sync = None
    if yes(prompter, "启用知识模块？", False):
        assembler = prompter.ask("知识由谁组装", default="plugin", choices=("plugin", "devclaw"))
        knowledge = {} if assembler == "plugin" else {"assembly": {"assembler": "devclaw"}}
        url = prompter.ask("知识仓库 HTTPS 地址（留空表示插件不拉取知识仓库）", default="")
        if url:
            knowledge["source"] = {"type": "git", "url": url,
                                   "ref": prompter.ask("分支、标签或 commit", default="main")}
    if yes(prompter, "启用产物同步模块？", False):
        candidates = [node["id"] for node in nodes if not node.get("terminal")]
        anchor = prompter.ask("从哪个节点完成起允许同步（节点 id）", default=candidates[0] if candidates else "",
                              choices=candidates or None)
        paths = []
        for node in nodes:
            for path in node.get("outputs", []):
                if not path.lower().endswith(".json") and path not in paths:
                    paths.append(path)
        artifact_sync = {"allowedFrom": f"{anchor}:done", "artifacts": {path: "[TODO: 简述]" for path in paths}}
        prompter.say("  已预填要上传的产物，简述写成 [TODO: 简述]，请在 modules/artifactSync.json 中补上")
    return knowledge, artifact_sync


def ask_hooks(prompter: Prompter) -> list:
    """逐个询问插件全局钩子（globalHooks 模块 hooks/ 下的目录），默认都不启用。"""
    from scaffold.modules.global_hooks.catalog import catalog

    available = catalog()
    if not available:
        return []
    prompter.say("── 插件全局钩子 ──\n  产物检查钩子始终启用；以下公共钩子按需选择")
    return [hook_id for hook_id, spec in available.items()
            if yes(prompter, f"启用 {spec.title}（{hook_id}）：{spec.description}？", False)]


def ask(prompter: Prompter, *, seed_plugin: dict | None = None, seeded: bool = False,
        existing_skills: list | None = None) -> dict:
    """返回 --answers 结构的回答。seeded 为 True（--from lite/fullstack）时可以保留样例的流程和模块配置。"""
    existing_skills = existing_skills or []
    answers = {"plugin": ask_plugin(prompter, seed_plugin or {})}
    if seeded and yes(prompter, "保留样例的流程、模块配置？", True):
        hooks = ask_hooks(prompter)
        if hooks:
            answers["globalHooks"] = {"hooks": hooks}
        prompter.say("── 7 自定义扩展 ──\n  将创建 hooks/（agents/ 可选，需要外挂子代理时再创建）")
        return answers
    answers["nodes"] = ask_nodes(prompter, existing_skills)
    answers["skills"] = ask_skills(prompter, answers["nodes"], existing_skills)
    for key, value in (("board", ask_board(prompter)), ("session", ask_session(prompter, answers["nodes"]))):
        if value is not None:
            answers[key] = value
    knowledge, artifact_sync = ask_modules(prompter, answers["nodes"])
    if knowledge is not None:
        answers["knowledge"] = knowledge
    if artifact_sync is not None:
        answers["artifactSync"] = artifact_sync
    hooks = ask_hooks(prompter)
    if hooks:
        answers["globalHooks"] = {"hooks": hooks}
    prompter.say("── 7 自定义扩展 ──\n  将创建 hooks/（agents/ 可选，需要外挂子代理时再创建）")
    return answers
