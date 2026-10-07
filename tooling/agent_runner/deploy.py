"""The executors of a deploy runner: on the production host, never an agent.

`error_incident.revision` answers which of the awaited fix commits the running
checkouts contain; `error_incident.hotfix` applies one approved fix commit, upgrades
the modules it touches, restarts and checks the server, and reverts when the
server does not come back healthy.

What runs on the host is the host's own configuration, never a lease's: a run
names a checkout and a commit, and the commands are these, read from the
environment:

    AGENT_RUNNER_DEPLOY_CHECKOUTS  JSON {"odoo": "/opt/odoo/odoo", ...}
    AGENT_RUNNER_DEPLOY_UPGRADE    command, `{modules}` = comma-separated names
    AGENT_RUNNER_DEPLOY_RESTART    command
    AGENT_RUNNER_DEPLOY_HEALTH     command; exit 0 = healthy
    AGENT_RUNNER_DEPLOY_HEALTH_WAIT  seconds to wait for health (default 120)
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .runner import Outcome, Permanent, Reporter
except ImportError:  # run as a script beside runner.py
    from runner import Outcome, Permanent, Reporter

GITHUB = "https://github.com/"
_SHA = re.compile(r"\A[0-9a-f]{7,40}\Z")
_REF = re.compile(r"\A[A-Za-z0-9._/-]{1,250}\Z")
_SAFE_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")


def _checkouts() -> dict[str, Path]:
    raw = json.loads(os.environ.get("AGENT_RUNNER_DEPLOY_CHECKOUTS", "{}"))
    return {name: Path(path) for name, path in raw.items()}


def _checkout(name: object) -> Path:
    checkouts = _checkouts()
    if not isinstance(name, str) or name not in checkouts:
        raise Permanent(f"this host serves no checkout named {name!r}")
    return checkouts[name]


def _git(cwd: Path, *args: str, token: str | None = None, check: bool = True) -> str:
    auth: tuple[str, ...] = ()
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        auth = ("-c", f"http.{GITHUB}.extraheader=AUTHORIZATION: basic {basic}")
    completed = subprocess.run(
        ["git", *_SAFE_GIT, *auth, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=False,
    )
    if check and completed.returncode:
        raise RuntimeError(f"git {args[0]} failed: {completed.stderr.strip()[-500:]}")
    return completed.stdout


def _contains(checkout: Path, commit: str) -> bool:
    if not _SHA.match(commit):
        return False
    # unknown to the checkout answers no, like a commit HEAD does not hold
    probe = subprocess.run(
        ["git", *_SAFE_GIT, "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=checkout,
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def revision(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    """Each checkout's running revision, and which awaited commits it holds."""
    awaited = lease["payload"].get("checkouts") or {}
    revisions: dict[str, str] = {}
    contained: list[str] = []
    for name, commits in awaited.items():
        checkouts = _checkouts()
        if name not in checkouts:
            reporter.event(f"no checkout {name!r} on this host", "warning")
            continue
        checkout = checkouts[name]
        # the running code is HEAD; a fetch only teaches git the commits it may
        # be asked about
        _git(checkout, "fetch", "--quiet", check=False)
        revisions[name] = _git(checkout, "rev-parse", "HEAD").strip()
        contained += [
            commit
            for commit in commits
            if isinstance(commit, str) and _contains(checkout, commit)
        ]
    return Outcome(result={"revisions": revisions, "contained": contained})


def _command(variable: str, **values: str) -> list[str] | None:
    template = os.environ.get(variable)
    if not template:
        return None
    return [part.format(**values) for part in shlex.split(template)]


def _run(command: list[str] | None, what: str) -> None:
    if command is None:
        return
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(
            f"{what} failed: {(completed.stderr or completed.stdout).strip()[-500:]}"
        )


def _healthy() -> bool:
    command = _command("AGENT_RUNNER_DEPLOY_HEALTH")
    if command is None:
        return True
    deadline = time.monotonic() + float(
        os.environ.get("AGENT_RUNNER_DEPLOY_HEALTH_WAIT", "120")
    )
    while True:
        if subprocess.run(command, capture_output=True, check=False).returncode == 0:
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(2)


def _modules(checkout: Path, before: str, after: str) -> list[str]:
    """The modules whose files the change touches: a file's nearest directory
    that holds a __manifest__.py."""
    modules = set()
    for path in _git(checkout, "diff", "--name-only", before, after).splitlines():
        for parent in (checkout / path).parents:
            if parent == checkout or checkout not in parent.parents:
                break
            if (parent / "__manifest__.py").is_file():
                modules.add(parent.name)
                break
    return sorted(modules)


def _activate(checkout: Path, before: str, after: str) -> list[str]:
    modules = _modules(checkout, before, after)
    if modules:
        _run(
            _command("AGENT_RUNNER_DEPLOY_UPGRADE", modules=",".join(modules)),
            "the upgrade",
        )
    _run(_command("AGENT_RUNNER_DEPLOY_RESTART"), "the restart")
    return modules


def hotfix(lease: dict[str, Any], reporter: Reporter) -> Outcome:
    payload = lease["payload"]
    checkout = _checkout(payload.get("checkout"))
    commit, branch = payload.get("commit"), payload.get("branch")
    if not (isinstance(commit, str) and _SHA.match(commit)):
        raise Permanent("a hotfix names its commit by sha")
    if not (isinstance(branch, str) and _REF.match(branch)):
        raise Permanent("a hotfix names a plain branch")
    if _git(checkout, "status", "--porcelain", "--untracked-files=no").strip():
        raise Permanent("the production checkout has local changes; nothing is applied")
    token = lease.get("credentials", {}).get("github", {}).get("token")
    url = f"{GITHUB}{payload['repository']}.git"
    remote = os.environ.get("AGENT_RUNNER_DEPLOY_REMOTE_URL", url).format(
        repository=payload["repository"]
    )
    _git(
        checkout,
        "fetch",
        "--quiet",
        remote,
        f"+refs/heads/{branch}:refs/remotes/hotfix/{branch}",
        token=token if remote.startswith(GITHUB) else None,
    )
    before = _git(checkout, "rev-parse", "HEAD").strip()
    if _contains(checkout, commit):
        return Outcome(
            result={"revision": before, "contained": [commit], "modules": []}
        )
    _git(
        checkout,
        "-c",
        "user.name=Autofix Hotfix",
        "-c",
        "user.email=autofix@localhost",
        "merge",
        "--no-ff",
        "--no-edit",
        "-m",
        f"Hotfix {commit[:12]} from {branch}\n\nAgent-Run: {lease['id']}",
        commit,
    )
    after = _git(checkout, "rev-parse", "HEAD").strip()
    reporter.event(f"applied {commit[:12]} on {checkout.name}", "progress")
    try:
        modules = _activate(checkout, before, after)
        if not _healthy():
            raise RuntimeError("the server did not come back healthy")
    except Exception as error:
        _git(checkout, "reset", "--quiet", "--hard", before)
        reporter.event(f"reverted to {before[:12]}: {error}", "error")
        _activate(checkout, after, before)
        raise Permanent(f"reverted: {error}") from error
    return Outcome(
        result={"revision": after, "contained": [commit], "modules": modules}
    )


EXECUTORS = {"error_incident.revision": revision, "error_incident.hotfix": hotfix}

__all__ = ["EXECUTORS", "hotfix", "revision"]
