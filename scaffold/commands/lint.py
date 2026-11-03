"""lint：只检查核心配置的结构和语义规则，以及编译配置是否过期；只读、不联网（input-config.md §7.2）。"""

from __future__ import annotations

from scaffold.build.pipeline import analyze
from scaffold.commands import CommandResult
from scaffold.lib.tree import Tree


def lint(root) -> CommandResult:
    return CommandResult(analyze(Tree(root), stale=True).report)
