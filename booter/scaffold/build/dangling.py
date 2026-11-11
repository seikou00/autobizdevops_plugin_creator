"""悬空引用检查（D71）：SKILL.md 正文里引用的技能资源和插件脚本，在插件中要真的存在。

从别的插件搬技能过来时，最容易漏掉的是正文引用的文件：技能自己的 templates/、references/、scripts/，
以及放在插件根目录 hooks/ 下、由技能直接调用的流程脚本。漏了不会有任何报错，要到模型执行到那一行才发现。

逐行扫描正文（跳过 frontmatter 和状态维护片段），取出两类路径：
- `${pluginPath}/…`：相对插件根目录，不限目录；
- 以资源目录（RESOURCE_DIRS）开头的相对路径，可以带 `./`、`../`。不带 `../` 时依次在技能目录、分组目录、
  skills/、插件根目录下找，任何一处有就算存在（`hooks/x.py` 常指插件根目录的 hooks/）；带 `../` 时只按技能目录解析。
  以 `skills/` 开头的相对路径按插件根目录解析。

不检查：URL、含占位符或通配符的路径（`<feature>`、`${var}`、`*`、`...`）、单独一个目录名，以及旧入口路径
（check 的 LEGACY_ENTRY_REF 负责，那些行应该删掉而不是补文件）。只报 warning：正文里也可能写到用户工程中的同名目录。

绝对路径另报 SKILL_REF_ABSOLUTE：`/…`、`~/…`、`C:/…`、`C:\…` 中含 skills 或资源目录一段的，是写死的某台机器上的
插件或技能位置，换个环境就找不到，应改成 `${pluginPath}/…`。不含这些目录的绝对路径（接口路由、斜杠命令等）不报。
"""

from __future__ import annotations

import posixpath
import re

from scaffold.lib import skillmd
from scaffold.lib.issues import warning

PLUGIN_ROOT = "${pluginPath}/"
RESOURCE_DIRS = ("templates", "references", "scripts", "hooks", "agents", "assets")
LEGACY_PATHS = ("hooks/update_state.py", "hooks/update_checkpoint.py", "hooks/route_checkpoint.py", "hooks/skip_node.py",
                "hooks/init_workspace.py", "${pluginPath}/inspect_state.py")
_TOKEN = re.compile(r"[A-Za-z0-9_.$\{\}/*<>~%@+\\-]+")
_PLACEHOLDER = re.compile(r"[$\{\}<>*%~@+\\]|\.\.\.")
# 绝对路径：/…、~/…、C:/…、C:\…；前面不能紧贴路径字符（否则是相对路径或 URL 的一部分）
_ABSOLUTE = re.compile(r"(?<![A-Za-z0-9_.$\{\}/*<>~%@+\\:-])(?:[A-Za-z]:[\\/]|~?/)[A-Za-z0-9_.$\{\}/*<>~%@+\\-]+")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def skill_files(tree) -> list:
    """skills/ 下全部 SKILL.md：集合根目录、分组、技能，以及技能目录里更深层的子技能（技能自己的资源）。"""
    return [path for path in tree.walk("skills") if path == "skills/SKILL.md" or path.endswith("/SKILL.md")]


def _candidates(token: str, directory: str):
    """token 可能指向的插件内路径；不是要检查的引用时返回 None。"""
    if token.startswith(PLUGIN_ROOT):
        rest = token[len(PLUGIN_ROOT):]
        if not rest or _PLACEHOLDER.search(rest):
            return None
        path = posixpath.normpath(rest)
        return None if path.startswith("..") else [path]
    if token.startswith("/") or _PLACEHOLDER.search(token):
        return None
    while token.startswith("./"):
        token = token[2:]
    segments = token.split("/")
    first = next((segment for segment in segments if segment != ".."), "")
    if segments[0] == "..":
        if first not in RESOURCE_DIRS:
            return None
        path = posixpath.normpath(posixpath.join(directory, token))
        return None if path.startswith("..") else [path]
    if first == "skills":
        return [posixpath.normpath(token)]
    if first not in RESOURCE_DIRS:
        return None
    bases = [directory]
    parent = posixpath.dirname(directory)
    while parent:
        bases.append(parent)
        parent = posixpath.dirname(parent)
    bases.append("")
    return [posixpath.normpath(posixpath.join(base, token)) for base in bases]


def _body_lines(text: str):
    """正文的 (行号, 行)，跳过 frontmatter 和状态维护片段；行号按整个文件计。"""
    front = skillmd.parse_frontmatter(text)
    body = text[front.body_start:]
    offset = text[:front.body_start].count("\n")
    span = None
    if skillmd.has_state(body):
        begin = body.find(skillmd.STATE_BEGIN)
        span = (body[:begin].count("\n"), body[:body.find(skillmd.STATE_END, begin)].count("\n"))
    for index, line in enumerate(body.splitlines()):
        if not (span and span[0] <= index <= span[1]):
            yield index + 1 + offset, line


def absolute_references(text: str) -> dict:
    """正文中写死的绝对路径：原文写法 → 出现的行号。只取含 skills 或资源目录一段的。"""
    found: dict = {}
    for number, line in _body_lines(text):
        for match in _ABSOLUTE.finditer(line):
            token = match.group(0).rstrip(".")
            rest = token[2:] if _DRIVE.match(token) else token.lstrip("~")
            if rest.startswith(("//", "\\\\")) or _PLACEHOLDER.search(rest.replace("\\", "/")):
                continue
            segments = [segment for segment in re.split(r"[\\/]", rest) if segment]
            if len(segments) >= 2 and any(segment in RESOURCE_DIRS + ("skills",) for segment in segments[:-1]):
                found.setdefault(token, []).append(number)
    return found


def references(text: str, directory: str) -> dict:
    """正文中要检查的引用：原文写法 → (候选路径, 出现的行号)。directory 是 SKILL.md 所在目录。"""
    found: dict = {}
    for number, line in _body_lines(text):
        for match in _TOKEN.finditer(line):
            token = match.group(0).rstrip(".")
            if "/" not in token.rstrip("/"):
                continue        # 不含目录分隔，或只是单独一个目录名（“放在 scripts/ 下”这类泛指）
            if any(token.endswith(legacy) for legacy in LEGACY_PATHS):
                continue
            candidates = _candidates(token, directory)
            if candidates is None:
                continue
            found.setdefault(token, (candidates, []))[1].append(number)
    return found


def _section(lines: list, number: int) -> str:
    for line in reversed(lines[:number - 1]):
        match = _HEADING.match(line)
        if match:
            return match.group(1).strip()
    return "（开头）"


def dangling_refs(tree, *, planned=(), skip=()) -> list:
    """planned 是这次生成将要写入的路径（首次生成时 runtime/ 等还不在磁盘上）；skip 是不检查的 SKILL.md
    （模块生成的技能，内容归脚手架）。"""
    planned = set(planned)
    planned_dirs = {path[:index] for path in planned for index, char in enumerate(path) if char == "/"}

    def exists(path: str) -> bool:
        return path in planned or path in planned_dirs or tree.is_file(path) or tree.is_dir(path)

    issues = []
    for path in skill_files(tree):
        if path in skip:
            continue
        text = skillmd.read_text(tree.read_bytes(path))
        lines = text.splitlines()
        directory = posixpath.dirname(path)
        for token, (candidates, numbers) in references(text, directory).items():
            if any(exists(candidate) for candidate in candidates):
                continue
            where = "、".join(str(number) for number in numbers)
            looked = candidates[0] if len(candidates) == 1 else "、".join(candidate for candidate in candidates)
            issues.append(warning(
                "SKILL_REF_DANGLING",
                f"第 {where} 行（小节“{_section(lines, numbers[0])}”）引用的 {token} 不存在（找过：{looked}）",
                file=path,
                hint="把这个文件或目录补进插件（从别的插件搬技能时，连同它引用的 templates/、references/、scripts/、"
                     "hooks/ 一起搬）；不再需要就删掉正文里的引用；指的是用户工程里的路径时可以忽略"))
        for token, numbers in absolute_references(text).items():
            tail = "/" + "/".join(re.split(r"[\\/]", token)[-2:])
            same = [rel for base in ("skills", "hooks", "agents") for rel in tree.walk(base) if rel.endswith(tail)][:3]
            where = "、".join(str(number) for number in numbers)
            issues.append(warning(
                "SKILL_REF_ABSOLUTE",
                f"第 {where} 行（小节“{_section(lines, numbers[0])}”）写死了绝对路径 {token}",
                file=path,
                hint="插件装在哪台机器的哪个目录是不固定的，改成 ${pluginPath}/… 或相对技能目录的路径"
                     + ("；插件里同名的文件：" + "、".join("${pluginPath}/" + rel for rel in same) if same else "")))
    return issues
