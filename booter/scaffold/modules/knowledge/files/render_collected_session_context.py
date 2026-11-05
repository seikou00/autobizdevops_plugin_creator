"""内置知识组装脚本（interfaces.md §4.5）：只负责会话内容中的知识段。

协议：stdin 读一个 JSON 请求（schema = autobiz.session.request.v1），stdout 输出
{"sessionContext", "agentmdLoadStatus", "message"}；日志写 stderr；不修改项目文件和知识目录。

组装顺序：
1. 调用同目录的 collect-knowledge.js（需要 Node 和 gray-matter）列出支持的发布单元，再逐个取所选单元的知识；
2. collector 不可用或单元不在它的列表中时，按清单映射加载系统 AGENTS.md 和单元文档；
3. 仍没有时回退 <localRepoPath>/AGENTS.md；
4. 始终读取 <sessionWorkspacePath>/AGENTS.md（会话工作区指令）和 CONTEXT.md（领域词汇表）。

插件可以整个替换这个文件，只要在同一路径实现上面的协议；doctor 不会覆盖被替换的文件。
gray-matter 由 doctor 在本目录执行 npm install 安装并随包带上；缺失时不在会话中安装（会话入口不得写文件），
直接按清单映射加载（README §9 第 7 条）。
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (str(ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import difflib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

import inspect_deploy_units as manifest_lib  # noqa: E402

COLLECTOR = HERE / "collect-knowledge.js"
COLLECT_TIMEOUT = 20
AGENTS_MD = "AGENTS.md"
CONTEXT_MD = "CONTEXT.md"
WORKSPACE_REF = "会话工作区指令"
WORKSPACE_SCOPE_ID = "会话工作区"
WORKSPACE_STATUS_ID = "本地工作区"
DOMAIN_STATUS_ID = "领域词汇表"
PREAMBLE = """## 必须执行的启动协议

1. 判断本次任务涉及哪些 deployUnit（见 <SCOPE> 映射表）。
2. 用文件读取、搜索或 shell 工具打开对应 <SYSTEM>、<UNIT> 段落的架构、领域、API、编码规范文档，以及 <SCOPE>「代码地址」下的相关代码，不凭包名、记忆路径、相似命名判断。
3. 任务跨多个 deployUnit 时，各单元规则同时适用，并分别说明验证结果。

本协议按「任务」生效，覆盖需求澄清、需求分析、向用户提问、设计、编码；不得因当前不是代码阶段而跳过。

## 指令反模式

- <SCOPE>、<SYSTEM>、<UNIT> 不表示任何文件已被读取；复述不算读取。
- 未用工具实际打开前，不得声称已读取，也不得据此开始实质分析、提问或答复。
- 路径不存在或无法访问时，说明未读取及原因，不得猜测内容。

## 指令优先级
skill 的工作步骤不构成跳过本协议的理由。冲突时按此顺序：当前用户请求 → 本启动协议 → <UNIT> 单元级约束 → <SYSTEM> 系统级约束 → 实际工程中的既有代码行为 → 通用框架或语言默认实践。"""


class CollectorError(RuntimeError):
    pass


def log(message: str) -> None:
    try:
        sys.stderr.write(f"[knowledge] {message}\n")
    except (OSError, ValueError):
        pass


def display_join(base, *parts, platform: str = "") -> str:
    sep = "\\" if platform == "win32" else "/"

    def normalize(text):
        return text.replace("/", "\\") if sep == "\\" else text.replace("\\", "/")

    text = normalize(str(base))
    tail = sep.join(normalize(str(part)).strip("\\/") for part in parts if str(part))
    if not tail:
        return text
    return (text.rstrip("\\/") + sep + tail) if text else tail


def read_nonempty(path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    return text if text.strip() else ""


def heading_slug(text: str) -> str:
    slug = re.sub(r"[^\w \-]", "", text.strip().lower(), flags=re.UNICODE)
    return slug.replace(" ", "-")


def unit_label(uid: str, ref: str) -> str:
    return f"{uid}（{ref}）" if ref else uid


def md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def attr(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# —— collector ——

def collector_unavailable() -> str:
    if not COLLECTOR.is_file():
        return "缺少 collect-knowledge.js"
    if shutil.which("node") is None:
        return "PATH 中找不到 node"
    if not (HERE / "node_modules" / "gray-matter").is_dir():
        return "collector 依赖 gray-matter 未安装"
    return ""


def run_collector(args: list, knowledge_dir: Path):
    command = ["node", str(COLLECTOR), *args, "--knowledgePath", str(knowledge_dir)]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=COLLECT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise CollectorError(f"collector 超时（{COLLECT_TIMEOUT} 秒）") from None
    except OSError as error:
        raise CollectorError(f"启动 collector 失败: {error}") from None
    stdout = completed.stdout.decode("utf-8", "replace").strip().lstrip("\ufeff")
    if completed.returncode != 0:
        detail = (completed.stderr.decode("utf-8", "replace") or stdout).strip()[:500] or "无任何输出"
        raise CollectorError(f"collector 失败（返回码 {completed.returncode}）: {detail}")
    try:
        return json.loads(stdout)
    except ValueError:
        raise CollectorError(f"collector 返回非法 JSON: {stdout[:200]}") from None


def collector_units(knowledge_dir: Path) -> list:
    payload = run_collector(["--listDeployUnits"], knowledge_dir)
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        raise CollectorError("--listDeployUnits 必须返回字符串数组")
    return list(dict.fromkeys(item.strip() for item in payload if item.strip()))


def collector_prompt(uid: str, knowledge_dir: Path) -> str:
    payload = run_collector(["--deployUnit", uid], knowledge_dir)
    prompt = payload.get("systemPrompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise CollectorError(f"deployUnit {uid} 没有返回非空的 systemPrompt")
    return prompt


# —— 组装 ——

def resolve_units(units, knowledge_dir: Path, platform: str):
    status, systems, sections, notes = [], [], [], []
    supported, reason = None, collector_unavailable()
    if units and not reason:
        try:
            supported = set(collector_units(knowledge_dir))
        except CollectorError as error:
            reason = str(error)
    if units and reason:
        notes.append(f"collector 不可用，已按清单映射加载: {reason}")
    pairs, duplicates = {}, frozenset()
    try:
        manifest = manifest_lib.load_manifest(knowledge_dir, strict_duplicates=False)
        pairs, duplicates = manifest_lib.unit_pairs(manifest), manifest.duplicates
    except manifest_lib.AgentsManifestError as error:
        if units:
            notes.append(str(error))
    seen_systems, seen_local = set(), set()
    refs, anchors = {}, {}
    for item in units:
        uid = str(item.get("deployUnitId", ""))
        pair = pairs.get(uid)
        ref = (pair[1].name if pair else "") or str(item.get("description", ""))
        refs[uid] = ref
        if uid in duplicates:
            status.append({"deployUnitId": uid, "path": display_join(knowledge_dir, platform=platform), "loaded": False,
                           "source": "remote", "message": f"清单中 deployUnitId 重复: {uid}"})
            continue
        miss = ""
        if supported is not None and uid in supported:
            try:
                sections.append({"deployUnitId": uid, "ref": ref, "content": collector_prompt(uid, knowledge_dir)})
                status.append({"deployUnitId": uid, "path": display_join(knowledge_dir, platform=platform),
                               "loaded": True, "source": "remote", "message": ""})
                continue
            except CollectorError as error:
                miss = str(error)
        elif supported is not None:
            similar = difflib.get_close_matches(uid, list(supported), n=3, cutoff=0.8)
            miss = f"deployUnit 不在 collector 列表中: {uid}" + (f"（相近: {', '.join(similar)}）" if similar else "")
        if pair is not None:
            system, unit = pair
            loaded = False
            system_path = manifest_lib.safe_join(knowledge_dir, system.agents_relpath())
            content = read_nonempty(system_path)
            if content and system.system_id not in seen_systems:
                seen_systems.add(system.system_id)
                systems.append({"systemId": system.system_id, "title": system.system_name or system.system_id,
                                "content": content})
            loaded = bool(content) or system.system_id in seen_systems
            if system.system_id in seen_systems:
                anchors[uid] = f"sys-{system.system_id}"
            if unit.agents_rel:
                unit_content = read_nonempty(manifest_lib.safe_join(knowledge_dir, unit.agents_rel))
                if unit_content:
                    sections.append({"deployUnitId": uid, "ref": ref, "content": unit_content})
                    loaded = True
            if loaded:
                status.append({"deployUnitId": uid, "path": display_join(knowledge_dir, system.agents_relpath(),
                                                                          platform=platform),
                               "loaded": True, "source": "remote", "message": "按清单映射加载" + (f"：{miss}" if miss else "")})
                continue
        local_repo = str(item.get("localRepoPath", "") or "")
        local_path = Path(local_repo) / AGENTS_MD if local_repo else None
        content = read_nonempty(local_path) if local_path else ""
        display = display_join(local_repo, AGENTS_MD, platform=platform) if local_repo else ""
        if content:
            key = str(local_path.resolve())
            if key not in seen_local:
                seen_local.add(key)
                sections.append({"deployUnitId": uid, "ref": ref, "content": content})
            status.append({"deployUnitId": uid, "path": display, "loaded": True, "source": "local",
                           "message": "知识目录未命中，已回退本地 AGENTS.md" + (f"：{miss}" if miss else "")})
            continue
        status.append({"deployUnitId": uid, "path": display or display_join(knowledge_dir, platform=platform),
                       "loaded": False, "source": "local",
                       "message": "；".join(part for part in (miss, "未找到本地 AGENTS.md") if part)})
    return status, systems, sections, notes, seen_local, refs, anchors


def compose(bindings, systems, workspace, sections, domain) -> str:
    lines = ["# 统一 Agent 指令", "", PREAMBLE]
    if bindings:
        lines += ["", "<SCOPE>", "", "## 适用范围",
                  "执行任务前先确认下面的工程映射；开发、排查与代码修改时优先在这些路径内进行（deployUnitId 链接指向下方对应知识段）：",
                  "", "| 引用范围 | deployUnitId | 代码地址（localRepoPath） |", "| --- | --- | --- |"]
        for binding in bindings:
            uid = md_cell(binding["deployUnitId"])
            cell = f"[{uid}](#{binding['anchor']})" if binding.get("anchor") else uid
            lines.append(f"| {md_cell(binding.get('ref') or '(未匹配知识库)')} | {cell} | "
                         f"{md_cell(binding.get('localRepoPath') or '(未提供)')} |")
        lines += ["", "</SCOPE>"]
    for section in systems:
        lines += ["", f'<SYSTEM id="sys-{section["systemId"]}" system="{attr(section["title"])}">', "",
                  section["content"].strip(), "", "</SYSTEM>"]
    blocks = []
    if workspace:
        blocks.append(f"## {WORKSPACE_REF}\n\n{workspace.strip()}")
    for section in sections:
        blocks.append(f"## {unit_label(section['deployUnitId'], section['ref'])}\n\n{section['content'].strip()}")
    if blocks:
        lines += ["", '<UNIT id="unit-section" unit="单元级">', "", "\n\n".join(blocks), "", "</UNIT>"]
    if domain:
        lines += ["", '<DOMAIN_CONTEXT id="domain-context" scope="项目级领域词汇表">', "", domain.strip(), "",
                  "</DOMAIN_CONTEXT>"]
    return "\n".join(lines)


def assemble(request: dict) -> dict:
    platform = str(request.get("platform") or "")
    units = [item for item in request.get("selectedDeployUnits") or [] if isinstance(item, dict)]
    knowledge_dir = Path(request.get("knowledgePath") or (ROOT / "sys"))
    workspace_dir = str(request.get("sessionWorkspacePath") or "").strip()
    status, systems, sections, notes, seen_local, refs, anchors = resolve_units(units, knowledge_dir, platform)
    workspace = read_nonempty(Path(workspace_dir) / AGENTS_MD) if workspace_dir else ""
    if workspace and str((Path(workspace_dir) / AGENTS_MD).resolve()) in seen_local:
        workspace = ""
    domain = read_nonempty(Path(workspace_dir) / CONTEXT_MD) if workspace_dir else ""
    with_section = {section["deployUnitId"] for section in sections}
    bindings = []
    if workspace:
        bindings.append({"deployUnitId": WORKSPACE_SCOPE_ID, "ref": WORKSPACE_REF, "localRepoPath": workspace_dir,
                         "anchor": heading_slug(WORKSPACE_REF)})
    for item in units:
        uid = str(item.get("deployUnitId", ""))
        ref = refs.get(uid, "")
        anchor = heading_slug(unit_label(uid, ref)) if uid in with_section else anchors.get(uid, "")
        bindings.append({"deployUnitId": uid, "ref": ref, "localRepoPath": item.get("localRepoPath", ""),
                         "anchor": anchor})
    session_status = []
    if workspace:
        session_status.append({"deployUnitId": WORKSPACE_STATUS_ID, "path": display_join(workspace_dir, AGENTS_MD,
                                                                                         platform=platform),
                               "loaded": True, "source": "local", "message": ""})
    if domain:
        session_status.append({"deployUnitId": DOMAIN_STATUS_ID, "path": display_join(workspace_dir, CONTEXT_MD,
                                                                                      platform=platform),
                               "loaded": True, "source": "local", "message": ""})
    counts = {"remote": 0, "local": 0, "miss": 0}
    for item in status:
        counts[item["source"] if item["loaded"] else "miss"] += 1
    message = f"remote {counts['remote']} / local {counts['local']} / 缺 {counts['miss']}"
    if notes:
        message += "；" + "；".join(notes)
    has_content = bool(bindings or systems or sections or domain)
    return {"sessionContext": compose(bindings, systems, workspace, sections, domain) if has_content else "",
            "agentmdLoadStatus": session_status + status, "message": message}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError as error:
        sys.stdout.write(json.dumps({"message": f"知识组装请求不是合法 JSON: {error}"}, ensure_ascii=False))
        return 1
    try:
        result = assemble(request if isinstance(request, dict) else {})
    except (OSError, manifest_lib.AgentsManifestError) as error:
        log(f"知识组装失败: {error}")
        result = {"sessionContext": "", "agentmdLoadStatus": [], "message": f"知识组装失败: {error}"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
