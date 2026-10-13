
from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

GITHUB = "https://github.com/"
TIMEOUT = 600
_SAFE = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.attributesFile=/dev/null",
)


def git_env(token: str | None = None, *, trusted: bool) -> dict[str, str]:
    if trusted:
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "AGENT_RUNNER_TOKEN"
        }
    else:
        env = {
            "PATH": os.environ["PATH"],
            "HOME": "/nonexistent",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ATTR_NOSYSTEM": "1",
        }
    env |= {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.{GITHUB}.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        }
    return env


def _verb(args: tuple[str, ...]) -> str:
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg == "-c":
            skip = True
        elif not arg.startswith("-"):
            return arg
    return "git"


def git(
    cwd: Path | None,
    *args: str,
    token: str | None = None,
    trusted: bool = False,
    check: bool = True,
    timeout: float = TIMEOUT,
    input: str | None = None,
) -> str:
    try:
        completed = subprocess.run(
            ["git", *_SAFE, *args],
            cwd=cwd,
            input=input,
            capture_output=True,
            text=True,
            env=git_env(token, trusted=trusted),
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"git {_verb(args)} timed out after {timeout:.0f}s"
        ) from error
    if check and completed.returncode:
        said = (completed.stderr.strip() or completed.stdout.strip())[-500:]
        raise RuntimeError(f"git {_verb(args)} failed: {said}")
    return completed.stdout


def git_bytes(
    cwd: Path | None,
    *args: str,
    input: bytes | None = None,
    trusted: bool = False,
    timeout: float = TIMEOUT,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *_SAFE, *args],
            cwd=cwd,
            input=input,
            capture_output=True,
            env=git_env(trusted=trusted),
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"git {_verb(args)} timed out after {timeout:.0f}s"
        ) from error


def is_ancestor(cwd: Path, commit: str, of: str, *, trusted: bool = False) -> bool:
    completed = subprocess.run(
        ["git", *_SAFE, "merge-base", "--is-ancestor", commit, of],
        cwd=cwd,
        capture_output=True,
        env=git_env(trusted=trusted),
        check=False,
        timeout=TIMEOUT,
    )
    return completed.returncode == 0
