"""One path contract for native Batch roots and nested task/module directories."""
from __future__ import annotations

import os
from pathlib import Path

import sys as _sys  # flowlib bootstrap：插件根目录和 skills/scripts 加入 sys.path
from pathlib import Path as _Path
for _entry in (_Path(__file__).resolve().parents[3], _Path(__file__).resolve().parents[3] / "skills" / "scripts"):
    if str(_entry) not in _sys.path:
        _sys.path.insert(0, str(_entry))
from flowlib.engineering_facts import git


def same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def batch_paths(batch: dict, requested: Path) -> tuple[Path, Path]:
    if not batch.get("worktreePath"):
        raise ValueError("engineering_batch_worktree_missing")
    root, task = Path(batch["worktreePath"]).resolve(), requested.resolve()
    if not task.is_dir() or not task.is_relative_to(root) or not same_path(git(task, "rev-parse", "--show-toplevel"), root):
        raise ValueError("engineering_worktree_mismatch")
    if batch.get("branchName") and git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != batch["branchName"]:
        raise ValueError("engineering_branch_mismatch")
    return root, task
