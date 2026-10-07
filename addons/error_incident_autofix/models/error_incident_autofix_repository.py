from pathlib import Path

import odoo
from odoo import fields, models
from odoo.modules.module import get_module_path
from odoo.tools import frozendict


def checkout_of(module: str) -> str | None:
    """The name of the git checkout ``module`` lives in -- `odoo`, `agromarin`,
    `l10n` -- or ``None``; the framework itself is `odoo`'s."""
    path = (
        get_module_path(module, display_warning=False)
        if module and module != "odoo"
        else odoo.__path__[0]
    )
    if not path:
        return None
    for directory in (Path(path).resolve(), *Path(path).resolve().parents):
        if (directory / ".git").exists():
            return directory.name
    return None


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
        checkout = checkout_of(module)
        if not checkout:
            return self.browse()
        return self.search([("checkout", "=", checkout)], limit=1)
