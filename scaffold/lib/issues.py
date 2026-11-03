"""Issue 与报告（interfaces.md §1.3，D43）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

FILE_ORDER = ("plugin.scaffold.json", "workflow.json", "modules/board.json", "modules/session.json",
              "modules/knowledge.json", "modules/artifactSync.json")


@dataclass(frozen=True)
class Issue:
    level: str          # "error" | "warning"
    code: str
    message: str
    file: str = ""      # 相对插件根，例如 workflow.json、skills/x/SKILL.md
    pointer: str = ""   # 文件内的 JSON Pointer；问题出在文件层面时为空
    hint: str = ""

    def to_json(self) -> dict:
        return {"level": self.level, "code": self.code, "file": self.file, "pointer": self.pointer,
                "message": self.message, "hint": self.hint}


def error(code, message, *, file="", pointer="", hint="") -> Issue:
    return Issue("error", code, message, file, pointer, hint)


def warning(code, message, *, file="", pointer="", hint="") -> Issue:
    return Issue("warning", code, message, file, pointer, hint)


def _pointer_key(pointer: str):
    parts = []
    for segment in pointer.split("/")[1:] if pointer else []:
        parts.append((0, int(segment), "") if segment.isdigit() else (1, 0, segment))
    return tuple(parts)


def sort_key(issue: Issue):
    rank = FILE_ORDER.index(issue.file) if issue.file in FILE_ORDER else len(FILE_ORDER)
    return (rank, issue.file, _pointer_key(issue.pointer), issue.code, issue.message)


class UsageError(Exception):
    """参数不合法、找不到入口文件或 workflow.json；CLI 映射为退出码 2。"""


class Report:
    def __init__(self, issues: Iterable[Issue] = ()):
        self.issues: list[Issue] = list(issues)

    def add(self, level, code, message, *, file="", pointer="", hint="") -> None:
        self.issues.append(Issue(level, code, message, file, pointer, hint))

    def extend(self, issues: Iterable[Issue]) -> None:
        self.issues.extend(issues)

    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    def has(self, code: str) -> bool:
        return any(issue.code == code for issue in self.issues)

    def failed(self, *, strict: bool = False) -> bool:
        return any(issue.level == "error" or strict for issue in self.issues)

    def sorted(self) -> list[Issue]:
        unique = list(dict.fromkeys(self.issues))
        return sorted(unique, key=sort_key)

    def to_json(self, *, written: Sequence[str] = (), strict: bool = False, **extra) -> dict:
        return {"ok": not self.failed(strict=strict), "issues": [issue.to_json() for issue in self.sorted()],
                "written": list(written), **extra}

    def to_text(self) -> str:
        lines = []
        for issue in self.sorted():
            where = " ".join(part for part in (issue.file, issue.pointer) if part)
            lines.append(f"{issue.level} {issue.code}  {where}".rstrip())
            for text in issue.message.splitlines() or [""]:
                lines.append(f"      {text}")
            if issue.hint:
                lines.append(f"      hint：{issue.hint}")
        return "\n".join(lines)
