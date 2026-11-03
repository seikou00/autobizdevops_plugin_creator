"""CLI 子命令的实现：每个命令返回 CommandResult，由 cli.py 输出并决定退出码。"""

from __future__ import annotations

from dataclasses import dataclass, field

from scaffold.lib.issues import Report


@dataclass
class CommandResult:
    report: Report
    extra: dict = field(default_factory=dict)       # 例如 doctor 的 {"changes": …}
    written: list = field(default_factory=list)
    text: str = ""                                  # 不加 --json 时在 Issue 之后输出的摘要
