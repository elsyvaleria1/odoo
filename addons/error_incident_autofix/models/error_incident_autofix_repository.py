import re
from pathlib import Path

import odoo
from odoo import fields, models
from odoo.modules.module import get_module_path
from odoo.tools import frozendict

_GITHUB_REMOTE = re.compile(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/*$")
_ORIGIN_URL = re.compile(
    r'^\[remote "origin"\]\s*$(?:\n[ \t]+.*$)*?\n[ \t]+url\s*=\s*(\S+)', re.MULTILINE
)


def _checkout_root(module: str) -> Path | None:
    """The working tree ``module`` lives in: the nearest directory holding a
    ``.git`` -- a directory in a clone, a file in a worktree."""
    path = (
        get_module_path(module, display_warning=False)
        if module and module != "odoo"
        else odoo.__path__[0]
    )
    if not path:
        return None
    for directory in (Path(path).resolve(), *Path(path).resolve().parents):
        if (directory / ".git").exists():
            return directory
    return None


def _git_config(root: Path) -> Path | None:
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git / "config"
    # a worktree: `.git` names its own git directory, whose `commondir` leads
    # to the repository's, where the remotes are
    text = dot_git.read_text(errors="replace").strip()
    if not text.startswith("gitdir:"):
        return None
    git_dir = (root / text.removeprefix("gitdir:").strip()).resolve()
    common = git_dir / "commondir"
    if common.is_file():
        git_dir = (git_dir / common.read_text().strip()).resolve()
    return git_dir / "config"


def github_repository_of(root: Path) -> str | None:
    """``owner/name`` of the GitHub repository a working tree's ``origin``
    fetches from, or ``None``."""
    config = _git_config(root)
    if config is None or not config.is_file():
        return None
    origin = _ORIGIN_URL.search(config.read_text(errors="replace"))
    remote = origin and _GITHUB_REMOTE.search(origin.group(1))
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
        cloned; by the checkout's directory name when it has no such remote."""
        root = _checkout_root(module)
        if root is None:
            return self.browse()
        if github := github_repository_of(root):
            found = self.search([("github_repository", "=ilike", github)], limit=1)
            if found:
                return found
        return self.search([("checkout", "=", root.name)], limit=1)
