import os
import re
import subprocess
from pathlib import Path

import odoo
from odoo import fields, models
from odoo.modules.module import get_module_path
from odoo.tools import frozendict

from odoo.addons.integration_github.tools import repository_domain

# github.com itself -- after `//`, `@` or nothing, never `notgithub.com`; `www.`
# or an ssh host alias (`github.com-odoo`) allowed -- with an ssh port or not,
# then owner/name
_GITHUB_REMOTE = re.compile(
    r"(?:^|[/@])(?:www\.)?github\.com(?:-[\w.-]+)?(?::\d+)?[:/]+"
    r"([\w.-]+/[\w.-]+?)(?:\.git)?/*$"
)


def _checkout_root(module: str) -> Path | None:
    """The working tree ``module`` lives in: the nearest directory holding a
    ``.git`` -- a directory in a clone, a file in a worktree."""
    if not module:
        return None
    path = (
        odoo.__path__[0]
        if module == "odoo"
        else get_module_path(module, display_warning=False)
    )
    if not path:
        return None
    for directory in (Path(path).resolve(), *Path(path).resolve().parents):
        if (directory / ".git").exists():
            return directory
    return None


def origin_url(root: Path) -> str | None:
    """The URL a working tree's `origin` fetches from, as git itself resolves
    it -- includes, `insteadOf`, a worktree's shared config -- or ``None``
    when there is no origin. No network: `--get-url` only reads the config."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-remote", "--get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", "/"),
                "GIT_TERMINAL_PROMPT": "0",
            },
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    url = done.stdout.strip()
    # git answers the remote's own name when there is no such remote
    return url if done.returncode == 0 and url and url != "origin" else None


def github_repository_of(url: str) -> str | None:
    """``owner/name`` of the GitHub repository ``url`` names, or ``None``."""
    remote = _GITHUB_REMOTE.search(url)
    return remote.group(1) if remote else None


class ErrorIncidentAutofixRepository(models.Model):
    _name = "error.incident.autofix.repository"
    _description = "Autofix Repository"
    _order = "checkout"
    _access_anchors = frozendict({"company": ""})

    checkout = fields.Char(
        required=True,
        help="The name of the git checkout a module lives in on the server: "
        "odoo, agromarin, l10n.",
    )
    github_repository = fields.Char(
        string="GitHub Repository",
        required=True,
        help="owner/name",
    )
    base_branch = fields.Char(
        required=True,
        help="The branch a fix starts from and its pull request targets.",
    )
    pass_without_checks = fields.Boolean(
        string="Pass Without Checks",
        help="This repository runs no CI: a fix's pull request that no check runs "
        "on counts as passing, so it can be merged or hotfixed once a person "
        "approves it. Off, such a fix waits in Testing for its checks.",
    )
    active = fields.Boolean(
        default=True,
    )

    _checkout_uniq = models.Constraint(
        "UNIQUE(checkout)",
        "A checkout maps to one repository.",
    )

    def _for_module(self, module: str) -> ErrorIncidentAutofixRepository:
        """The repository of the checkout ``module`` lives in: by the GitHub
        repository its ``origin`` fetches from, which names it wherever it is
        cloned; by the checkout's directory name only when it has no origin.
        An origin that is no mapped GitHub repository -- a fork, another host
        -- is no repository's."""
        root = _checkout_root(module)
        if root is None:
            return self.browse()
        url = origin_url(root)
        if url is None:
            return self.search([("checkout", "=", root.name)], limit=1)
        if github := github_repository_of(url):
            return self.search(repository_domain("github_repository", github), limit=1)
        return self.browse()
