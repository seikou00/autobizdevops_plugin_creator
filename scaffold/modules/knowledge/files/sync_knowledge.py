"""pull_knowledge：拉取知识仓库到插件的 sys/（interfaces.md §3.3.9，来自 lite 的 sync_agents.py）。

先在临时目录克隆并校验清单，成功后再替换 sys/；HTTPS 失败时回退 SSH。只更新知识目录，不回写任何配置文件。
仓库地址取自 runtime/config/knowledge.json 的 source。始终以 0 退出，用 ok 字段表示结果。
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (str(ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import os  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from typing import List, Optional  # noqa: E402
from urllib.parse import urlsplit, urlunsplit  # noqa: E402

import inspect_deploy_units as manifest_lib  # noqa: E402

SCHEMA_VERSION = "autobizdevops.agents.sync.v1"
HTTPS_CLONE_TIMEOUT = 20
KILL_REAP_SECONDS = 5
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
GIT_CONFIG = ["-c", "http.lowSpeedLimit=1", "-c", "http.lowSpeedTime=15"]


class CloneUnavailable(RuntimeError):
    """同一 URL 的两种 clone 方式都失败，允许改用备用地址。"""


def log(message: str) -> None:
    try:
        sys.stderr.write(f"[sync_knowledge {time.strftime('%H:%M:%S')}] {message}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def mask_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if not parts.username and not parts.password:
            return url
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
    except ValueError:
        return url
    return urlunsplit((parts.scheme, f"***@{host}", parts.path, parts.query, parts.fragment))


def kill_tree(process: subprocess.Popen) -> None:
    """Windows 的 git.exe 外壳之下还有继承输出管道的子进程，要整棵结束。"""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False,
                           timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def run_git(args: List[str], *, cwd: Optional[Path] = None, timeout: Optional[float] = None):
    described = " ".join(mask_url(arg) if "://" in arg else arg for arg in args)
    log(f"git {described}")
    process = subprocess.Popen(["git", *GIT_CONFIG, *args], cwd=str(cwd) if cwd else None,
                               env={**os.environ, **GIT_ENV}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace", start_new_session=os.name != "nt")
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        try:
            process.communicate(timeout=KILL_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        raise
    except BaseException:
        kill_tree(process)
        raise
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def git_error(completed, action: str) -> str:
    detail = "\n".join(text.strip() for text in (completed.stderr, completed.stdout) if text and text.strip())
    return f"{action} 失败: {detail or f'git 返回码 {completed.returncode}'}"


def rmtree(path: Path) -> None:
    """Windows 上 git 给 .git/objects 下的文件加了只读位，去掉后再删。"""

    def clear_readonly(func, target, _info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_readonly)
    else:
        shutil.rmtree(path, onerror=clear_readonly)


def clone(url: str, ref: str, dest: Path, timeout: Optional[float]) -> str:
    if dest.exists():
        rmtree(dest)
    try:
        completed = run_git(["clone", "--depth", "1", "--branch", ref, url, str(dest)], timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CloneUnavailable(f"克隆超时（{timeout:g} 秒）") from None
    if completed.returncode != 0:
        if dest.exists():
            rmtree(dest)
        try:
            fallback = run_git(["clone", "--depth", "1", url, str(dest)], timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CloneUnavailable(f"克隆超时（{timeout:g} 秒）") from None
        if fallback.returncode != 0:
            raise CloneUnavailable(git_error(fallback, "克隆"))
        checkout = run_git(["checkout", ref], cwd=dest)
        if checkout.returncode != 0:
            raise RuntimeError(git_error(checkout, f"切换到 {ref}"))
    revision = run_git(["rev-parse", "HEAD"], cwd=dest)
    return revision.stdout.strip() if revision.returncode == 0 else ""


def fetch(url: str, ref: str, dest: Path, ssh_url: str) -> dict:
    https = url.strip().lower().startswith("https://")
    try:
        return {"commit": clone(url, ref, dest, HTTPS_CLONE_TIMEOUT if https else None),
                "transport": "https" if https else "other"}
    except CloneUnavailable as https_error:
        if not https or not ssh_url:
            raise
        log(f"HTTPS 克隆失败，改用 SSH: {https_error}")
        try:
            return {"commit": clone(ssh_url, ref, dest, None), "transport": "ssh"}
        except RuntimeError as ssh_error:
            raise RuntimeError(f"HTTPS 克隆失败: {https_error}\nSSH 兜底失败: {ssh_error}") from ssh_error


def payload(knowledge_dir: Path, repo: dict) -> dict:
    manifest = manifest_lib.load_manifest(knowledge_dir)
    systems, supported = manifest_lib.systems_payload(knowledge_dir, manifest)
    ready = sum(1 for system in systems if system["agentsReady"])
    for system in systems:
        for unit in system["deployUnits"]:
            unit.pop("description", None)
    _, manifest_rel = manifest_lib.manifest_settings()
    return {"ok": True, "schemaVersion": SCHEMA_VERSION,
            "message": f"agents 仓库已同步：{len(systems)} 个系统、{len(supported)} 个发布单元，"
                       f"AGENTS.md 就绪 {ready}/{len(systems)}",
            "repo": repo, "knowledge_path": str(knowledge_dir), "supported_deploy_units": supported,
            "systems": systems, "supported_deploy_units_source": manifest_rel}


def sync() -> dict:
    from runtime.common.engine import file_lock

    config = manifest_lib.knowledge_config()
    source = config.get("source") or {}
    url = str(source.get("url") or "").strip()
    if not url:
        raise ValueError("runtime/config/knowledge.json 没有声明 source.url")
    ref = source.get("ref") or "main"
    ssh_url = str(source.get("sshUrl") or "").strip()
    destination = ROOT / config.get("root", "sys")
    with file_lock(ROOT / ".knowledge.lock"):
        with tempfile.TemporaryDirectory(prefix=".knowledge-sync-", dir=str(ROOT)) as temporary:
            staging = Path(temporary)
            staged = staging / destination.name
            info = fetch(url, ref, staged, ssh_url)
            repo = {"url": url, "sshUrl": ssh_url, "ref": ref, **info}
            payload(staged, repo)
            backup = staging / "previous"
            if destination.exists():
                destination.rename(backup)
            try:
                staged.rename(destination)
            except OSError:
                if backup.exists():
                    backup.rename(destination)
                raise
            if backup.exists():
                rmtree(backup)
            return payload(destination, repo)


def main(argv=None) -> int:
    from runtime.common import cli

    def action():
        try:
            return sync()
        except (manifest_lib.AgentsManifestError, OSError, RuntimeError, ValueError) as error:
            log(f"同步失败: {error}")
            return {"ok": False, "schemaVersion": SCHEMA_VERSION, "message": str(error), "errors": [str(error)]}

    return cli.run(action, always_zero=True)


if __name__ == "__main__":
    sys.exit(main())
