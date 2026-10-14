from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .gitops import GITHUB, git, git_bytes, is_ancestor
    from .runner import Outcome, Permanent, Reporter, run_in_session
except ImportError:
    from gitops import GITHUB, git, git_bytes, is_ancestor
    from runner import Outcome, Permanent, Reporter, run_in_session

_SHA = re.compile(r"\A[0-9a-f]{7,40}\Z")
_REF = re.compile(r"\A(?!-)[A-Za-z0-9._/-]{1,250}\Z")
HEALTHY = "refs/odoo-runner/healthy"
COMMAND_TIMEOUT = 300
HEALTH_CALL_TIMEOUT = 30


def _checkouts() -> dict[str, Path]:
    raw = json.loads(os.environ.get("RUNNER_DEPLOY_CHECKOUTS", "{}"))
    return {name: Path(path) for name, path in raw.items()}


def _checkout(name: object) -> Path:
    checkouts = _checkouts()
    if not isinstance(name, str) or name not in checkouts:
        raise Permanent(f"this host serves no checkout named {name!r}")
    return checkouts[name]


def _git(cwd: Path, *args: str, **kwargs: Any) -> str:
    return git(cwd, *args, trusted=True, **kwargs)


def _contains(checkout: Path, commit: str) -> bool:
    return bool(_SHA.match(commit)) and is_ancestor(
        checkout, commit, "HEAD", trusted=True
    )


def revision(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    awaited = lease["payload"].get("checkouts") or {}
    revisions: dict[str, str] = {}
    contained: list[str] = []
    for name, commits in awaited.items():
        checkouts = _checkouts()
        if name not in checkouts:
            reporter.event(f"no checkout {name!r} on this host", "warning")
            continue
        checkout = checkouts[name]
        _git(checkout, "fetch", "--quiet", check=False)
        revisions[name] = _git(checkout, "rev-parse", "HEAD").strip()
        contained += [
            commit
            for commit in commits
            if isinstance(commit, str) and _contains(checkout, commit)
        ]
    return Outcome(result={"revisions": revisions, "contained": contained})


def _host_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key != "RUNNER_TOKEN"}


def _command(variable: str, modules: str = "") -> list[str] | None:
    template = os.environ.get(variable)
    if not template:
        return None
    return [part.replace("{modules}", modules) for part in shlex.split(template)]


def _run(
    command: list[str] | None, what: str, timeout: float = COMMAND_TIMEOUT
) -> None:
    if command is None:
        return
    try:
        finished = run_in_session(command, env=_host_env(), timeout=timeout)
    except OSError as error:
        raise RuntimeError(f"{what} cannot start: {error}") from error
    if finished.ended:
        raise RuntimeError(f"{what} timed out after {timeout:.0f}s")
    if finished.returncode:
        said = (finished.stderr or finished.stdout).strip()[-500:]
        raise RuntimeError(f"{what} failed: {said}")


def _healthy() -> bool:
    command = _command("RUNNER_DEPLOY_HEALTH")
    if command is None:
        return True
    deadline = time.monotonic() + float(
        os.environ.get("RUNNER_DEPLOY_HEALTH_WAIT", "120")
    )
    while True:
        left = deadline - time.monotonic()
        try:
            if (
                subprocess.run(
                    command,
                    capture_output=True,
                    env=_host_env(),
                    check=False,
                    timeout=max(min(HEALTH_CALL_TIMEOUT, left), 1),
                ).returncode
                == 0
            ):
                return True
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() > deadline:
            return False
        time.sleep(2)


def _modules(checkout: Path, before: str, after: str) -> list[str]:
    manifests = {
        PurePosixPath(path).parent
        for path in _git(checkout, "ls-tree", "-r", "-z", "--name-only", after).split(
            "\0"
        )
        if PurePosixPath(path).name == "__manifest__.py"
    }
    changed = _git(
        checkout, "diff", "--no-renames", "--name-only", "-z", before, after
    ).split("\0")
    modules = set()
    for path in filter(None, changed):
        for parent in PurePosixPath(path).parents:
            if parent in manifests:
                modules.add(parent.name)
                break
    return sorted(modules)


def _activate(modules: list[str]) -> None:
    upgrade = _command("RUNNER_DEPLOY_UPGRADE", ",".join(modules)) if modules else None
    upgrade_timeout = float(os.environ.get("RUNNER_DEPLOY_UPGRADE_TIMEOUT", "3600"))
    stop = _command("RUNNER_DEPLOY_STOP")
    start = _command("RUNNER_DEPLOY_START")
    if stop and start:
        _run(stop, "the stop")
        try:
            _run(upgrade, "the upgrade", upgrade_timeout)
        finally:
            _run(start, "the start")
        return
    _run(upgrade, "the upgrade", upgrade_timeout)
    _run(_command("RUNNER_DEPLOY_RESTART"), "the restart")


def _fetch(
    checkout: Path, payload: dict[str, Any], branch: str, into: str, token: str | None
) -> str:
    url = f"{GITHUB}{payload['repository']}.git"
    remote = os.environ.get("RUNNER_DEPLOY_REMOTE_URL", url).replace(
        "{repository}", payload["repository"]
    )
    _git(
        checkout,
        "fetch",
        "--quiet",
        remote,
        f"+refs/heads/{branch}:{into}",
        token=token if remote.startswith(GITHUB) else None,
    )
    return into


def _hotfix_of(checkout: Path, commit: str) -> str | None:
    found = _git(
        checkout,
        "log",
        "--format=%H",
        "-n1",
        "--fixed-strings",
        f"--grep=Hotfix-Of: {commit}",
        "HEAD",
    )
    return found.strip() or None


def _confirmed_running(checkout: Path, applied: str) -> bool:
    healthy = _git(
        checkout, "rev-parse", "--verify", "--quiet", HEALTHY, check=False
    ).strip()
    return bool(healthy) and (
        is_ancestor(checkout, applied, healthy, trusted=True)
        and is_ancestor(checkout, healthy, "HEAD", trusted=True)
    )


def _patch(checkout: Path, before: str, after: str, *options: str) -> bytes:
    done = git_bytes(
        checkout,
        "diff-tree",
        "-p",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *options,
        before,
        after,
        trusted=True,
    )
    if done.returncode:
        raise RuntimeError(
            f"git diff-tree failed: {done.stderr.decode(errors='replace')[-500:]}"
        )
    return done.stdout


def _apply(
    checkout: Path, patch: bytes, *options: str
) -> subprocess.CompletedProcess[bytes]:
    return git_bytes(
        checkout,
        "apply",
        "--whitespace=nowarn",
        *options,
        "-",
        input=patch,
        trusted=True,
        timeout=COMMAND_TIMEOUT,
    )


def _change_present(checkout: Path, applied: str) -> bool:
    patch = _patch(checkout, f"{applied}^", applied, "-U0")
    return (
        not patch.strip()
        or _apply(checkout, patch, "--reverse", "--check", "--unidiff-zero").returncode
        == 0
    )


def hotfix(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    payload = lease["payload"]
    checkout = _checkout(payload.get("checkout"))
    commit = payload.get("commit")
    branch, base_branch = payload.get("branch"), payload.get("base_branch")
    if not (isinstance(commit, str) and _SHA.match(commit)):
        raise Permanent("a hotfix names its commit by sha")
    for name in (branch, base_branch):
        if not (isinstance(name, str) and _REF.match(name) and ".." not in name):
            raise Permanent("a hotfix names its branch and its base as plain branches")
    if _git(checkout, "status", "--porcelain", "--untracked-files=no").strip():
        raise Permanent("the production checkout has local changes; nothing is applied")
    token = lease.get("credentials", {}).get("github", {}).get("token")
    fix_ref = _fetch(checkout, payload, branch, f"refs/remotes/hotfix/{branch}", token)
    base_ref = _fetch(
        checkout, payload, base_branch, f"refs/remotes/hotfix-base/{base_branch}", token
    )
    if not is_ancestor(checkout, commit, fix_ref, trusted=True):
        raise Permanent(f"{commit[:12]} is not on {branch}")
    base = _git(checkout, "merge-base", commit, base_ref).strip()
    head = _git(checkout, "rev-parse", "HEAD").strip()
    modules = _modules(checkout, base, commit)

    if _contains(checkout, commit):
        return Outcome(result={"revision": head, "contained": [commit], "modules": []})
    patch = _patch(checkout, base, commit)
    if not patch.strip():
        raise Permanent(
            f"{commit[:12]} adds nothing to {base_branch}: it is merged there "
            "already, and reaches production with the base's deploy"
        )
    applied = _hotfix_of(checkout, commit)
    if applied and _change_present(checkout, applied):
        return _applied_already(checkout, applied, head, modules, commit, reporter)

    done = _apply(checkout, patch, "--3way", "--index")
    if done.returncode:
        _git(checkout, "reset", "--quiet", "--hard", head)
        said = (done.stderr or done.stdout).decode(errors="replace").strip()[-500:]
        raise Permanent(
            f"the fix does not apply to production's revision {head[:12]}: {said}"
        )
    if not _git(checkout, "diff", "--cached", "--name-only").strip():
        _git(checkout, "reset", "--quiet", "--hard", head)
        if applied:
            return _applied_already(checkout, applied, head, modules, commit, reporter)
        return Outcome(result={"revision": head, "contained": [commit], "modules": []})
    _git(
        checkout,
        "-c",
        "user.name=Autofix Hotfix",
        "-c",
        "user.email=autofix@localhost",
        "commit",
        "--quiet",
        "--no-verify",
        "-m",
        f"Hotfix {commit[:12]} from {branch}\n\nHotfix-Of: {commit}\nRunner-Job: {lease['id']}",
    )
    after = _git(checkout, "rev-parse", "HEAD").strip()
    reporter.event(f"applied {commit[:12]} on {checkout.name}", "progress")
    return _activate_or_revert(checkout, head, after, modules, commit, reporter)


def _applied_already(
    checkout: Path,
    applied: str,
    head: str,
    modules: list[str],
    commit: str,
    reporter: Reporter,
) -> Outcome:
    if _confirmed_running(checkout, applied):
        return Outcome(result={"revision": head, "contained": [commit], "modules": []})
    reporter.event(
        f"{commit[:12]} is applied but not confirmed running; activating", "progress"
    )
    before = (
        _git(checkout, "rev-parse", f"{applied}^").strip() if applied == head else head
    )
    return _activate_or_revert(checkout, before, head, modules, commit, reporter)


def _activate_or_revert(
    checkout: Path,
    before: str,
    after: str,
    modules: list[str],
    commit: str,
    reporter: Reporter,
) -> Outcome:
    try:
        _activate(modules)
        if not _healthy():
            raise RuntimeError("the server did not come back healthy")
    except Exception as error:
        _revert(checkout, before, after, modules, error, reporter)
    _git(checkout, "update-ref", HEALTHY, after)
    return Outcome(
        result={"revision": after, "contained": [commit], "modules": modules}
    )


def _revert(
    checkout: Path,
    before: str,
    after: str,
    modules: list[str],
    error: Exception,
    reporter: Reporter,
) -> None:
    if before == after:
        raise Permanent(
            f"the applied fix does not run healthy and cannot be reverted here: "
            f"{error}; production needs a person"
        ) from error
    try:
        _git(checkout, "reset", "--quiet", "--hard", before)
        reporter.event(f"reverted to {before[:12]}: {error}", "error")
        _activate(modules)
        healthy = _healthy()
    except Exception as revert_error:
        raise Permanent(
            f"reverted the code after {error}, but the revert failed: {revert_error}; "
            "production needs a person"
        ) from revert_error
    if not healthy:
        raise Permanent(
            f"reverted after {error}, but the server is still not healthy; "
            "production needs a person"
        ) from error
    raise Permanent(f"reverted: {error}") from error


EXECUTORS = {"error_incident.revision": revision, "error_incident.hotfix": hotfix}

__all__ = ["EXECUTORS", "hotfix", "revision"]
