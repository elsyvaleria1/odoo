"""The executors of a deploy runner: on the production host, never an agent.

`error_incident.revision` answers which of the awaited fix commits the running
checkouts contain. `error_incident.hotfix` applies one approved fix to a
running checkout: the fix's own commits -- what its branch adds to the base it
was cut from, never the base's unreleased commits -- cherry-picked onto the
running revision as one commit, then the modules they touch upgraded, the
server restarted and checked. When the server does not come back healthy, the
code is reverted, the modules upgraded and the server restarted again; the
database is not restored, so a fix whose upgrade migrated data is undone in
code only.

What runs on the host is the host's own configuration, never a lease's: a run
names a checkout and a commit, and the commands are these, read from the
environment:

    AGENT_RUNNER_DEPLOY_CHECKOUTS     JSON {"odoo": "/opt/odoo/odoo", ...}
    AGENT_RUNNER_DEPLOY_UPGRADE       command, `{modules}` = comma-separated names
    AGENT_RUNNER_DEPLOY_RESTART       command
    AGENT_RUNNER_DEPLOY_STOP          command; with START, the server is stopped
    AGENT_RUNNER_DEPLOY_START         for the upgrade instead of restarted after it
    AGENT_RUNNER_DEPLOY_HEALTH        command; exit 0 = healthy
    AGENT_RUNNER_DEPLOY_HEALTH_WAIT   seconds to wait for health (default 120)
    AGENT_RUNNER_DEPLOY_UPGRADE_TIMEOUT  seconds an upgrade may take (default 3600)
    AGENT_RUNNER_DEPLOY_REMOTE_URL    fetch URL template, `{repository}` = owner/name

A revision that passed its health check is recorded in the checkout as
`refs/agent-runner/healthy`: an attempt that finds the fix already applied
but not confirmed healthy -- a runner killed between the two -- activates it
again instead of reporting it deployed.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .gitops import GITHUB, git, is_ancestor
    from .runner import Outcome, Permanent, Reporter
except ImportError:  # run as a script beside runner.py
    from gitops import GITHUB, git, is_ancestor
    from runner import Outcome, Permanent, Reporter

_SHA = re.compile(r"\A[0-9a-f]{7,40}\Z")
_REF = re.compile(r"\A(?!-)[A-Za-z0-9._/-]{1,250}\Z")
HEALTHY = "refs/agent-runner/healthy"
COMMAND_TIMEOUT = 300
HEALTH_CALL_TIMEOUT = 30


def _checkouts() -> dict[str, Path]:
    raw = json.loads(os.environ.get("AGENT_RUNNER_DEPLOY_CHECKOUTS", "{}"))
    return {name: Path(path) for name, path in raw.items()}


def _checkout(name: object) -> Path:
    checkouts = _checkouts()
    if not isinstance(name, str) or name not in checkouts:
        raise Permanent(f"this host serves no checkout named {name!r}")
    return checkouts[name]


def _git(cwd: Path, *args: str, **kwargs: Any) -> str:
    # production's checkouts are the host's own, configured by it: its
    # credentials and settings apply
    return git(cwd, *args, trusted=True, **kwargs)


def _contains(checkout: Path, commit: str) -> bool:
    return bool(_SHA.match(commit)) and is_ancestor(
        checkout, commit, "HEAD", trusted=True
    )


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


def _host_env() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key != "AGENT_RUNNER_TOKEN"
    }


def _command(variable: str, modules: str = "") -> list[str] | None:
    template = os.environ.get(variable)
    if not template:
        return None
    # only `{modules}` is substituted: a command's other braces are its own
    return [part.replace("{modules}", modules) for part in shlex.split(template)]


def _run(
    command: list[str] | None, what: str, timeout: float = COMMAND_TIMEOUT
) -> None:
    if command is None:
        return
    # a session of its own: a command that runs out of time is killed with
    # everything it started, not left upgrading under the revert
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_host_env(),
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError(f"{what} timed out after {timeout:.0f}s") from error
    if process.returncode:
        raise RuntimeError(f"{what} failed: {(stderr or stdout).strip()[-500:]}")


def _healthy() -> bool:
    command = _command("AGENT_RUNNER_DEPLOY_HEALTH")
    if command is None:
        return True
    deadline = time.monotonic() + float(
        os.environ.get("AGENT_RUNNER_DEPLOY_HEALTH_WAIT", "120")
    )
    while True:
        # a call that hangs is cut at the wait's end, never runs past it
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
    """The modules whose files the change touches: a file's nearest directory
    that holds a __manifest__.py."""
    modules = set()
    for path in _git(checkout, "diff", "--name-only", "-z", before, after).split("\0"):
        if not path:
            continue
        for parent in (checkout / path).parents:
            if parent == checkout or checkout not in parent.parents:
                break
            if (parent / "__manifest__.py").is_file():
                modules.add(parent.name)
                break
    return sorted(modules)


def _activate(modules: list[str]) -> None:
    """Upgrade ``modules`` and run the code that is now checked out."""
    upgrade = (
        _command("AGENT_RUNNER_DEPLOY_UPGRADE", ",".join(modules)) if modules else None
    )
    upgrade_timeout = float(
        os.environ.get("AGENT_RUNNER_DEPLOY_UPGRADE_TIMEOUT", "3600")
    )
    stop = _command("AGENT_RUNNER_DEPLOY_STOP")
    start = _command("AGENT_RUNNER_DEPLOY_START")
    if stop and start:
        _run(stop, "the stop")
        try:
            _run(upgrade, "the upgrade", upgrade_timeout)
        finally:
            _run(start, "the start")
        return
    _run(upgrade, "the upgrade", upgrade_timeout)
    _run(_command("AGENT_RUNNER_DEPLOY_RESTART"), "the restart")


def _fetch(
    checkout: Path, payload: dict[str, Any], branch: str, into: str, token: str | None
) -> str:
    url = f"{GITHUB}{payload['repository']}.git"
    remote = os.environ.get("AGENT_RUNNER_DEPLOY_REMOTE_URL", url).replace(
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
    """The commit by which an earlier hotfix applied ``commit`` -- it names it
    in a `Hotfix-Of` trailer -- when the running revision holds one."""
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
    """Whether the revision that applied the fix was confirmed healthy: it is
    in the revision last confirmed, and that one in what runs -- a normal deploy
    since, which does not move the marker, does not unconfirm it."""
    healthy = _git(
        checkout, "rev-parse", "--verify", "--quiet", HEALTHY, check=False
    ).strip()
    return bool(healthy) and (
        is_ancestor(checkout, applied, healthy, trusted=True)
        and is_ancestor(checkout, healthy, "HEAD", trusted=True)
    )


def _change_present(checkout: Path, base: str, commit: str) -> bool:
    """Whether the running tree holds what the fix changed: its diff, reversed,
    applies cleanly -- false once a person reverted it."""
    diff = _git(checkout, "diff", "--binary", base, commit)
    if not diff.strip():
        return True
    check = subprocess.run(
        ["git", "apply", "--reverse", "--check", "-"],
        cwd=checkout,
        input=diff,
        capture_output=True,
        text=True,
        env=_host_env(),
        check=False,
        timeout=COMMAND_TIMEOUT,
    )
    return check.returncode == 0


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
        # production's own deploy brought it: activating it is that deploy's
        return Outcome(result={"revision": head, "contained": [commit], "modules": []})
    applied = _hotfix_of(checkout, commit)
    if applied and not _change_present(checkout, base, commit):
        # a person reverted the hotfix since: it is applied no more
        applied = None
    if applied:
        if _confirmed_running(checkout, applied):
            return Outcome(
                result={"revision": head, "contained": [commit], "modules": []}
            )
        # applied, but never confirmed running: an earlier attempt died
        # between the two; it can be reverted while it is still the tip
        reporter.event(
            f"{commit[:12]} is applied but not confirmed running; activating",
            "progress",
        )
        before = (
            _git(checkout, "rev-parse", f"{applied}^").strip()
            if applied == head
            else head
        )
        return _activate_or_revert(checkout, before, head, modules, commit, reporter)

    try:
        _git(checkout, "cherry-pick", "--no-commit", f"{base}..{commit}")
    except RuntimeError as error:
        _git(checkout, "cherry-pick", "--abort", check=False)
        _git(checkout, "reset", "--quiet", "--hard", head)
        raise Permanent(
            f"the fix does not apply to production's revision {head[:12]}: {error}"
        ) from error
    if not _git(checkout, "diff", "--cached", "--name-only").strip():
        # production holds the change already, by another way: nothing to apply
        _git(checkout, "reset", "--quiet", "--hard", head)
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
        f"Hotfix {commit[:12]} from {branch}\n\nHotfix-Of: {commit}\nAgent-Run: {lease['id']}",
    )
    after = _git(checkout, "rev-parse", "HEAD").strip()
    reporter.event(f"applied {commit[:12]} on {checkout.name}", "progress")
    return _activate_or_revert(checkout, head, after, modules, commit, reporter)


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
    """Put the code back as it was, upgrade and restart again; always a
    permanent failure -- another attempt would apply the same fix again."""
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
