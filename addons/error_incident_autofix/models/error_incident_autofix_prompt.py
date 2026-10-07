from odoo import api, fields, models
from odoo.tools import frozendict


class ErrorIncidentAutofixPrompt(models.Model):
    """What the agent is told, versioned: a run records the version it was
    given, so a verdict can be read against the instructions that produced
    it."""

    _name = "error.incident.autofix.prompt"
    _description = "Autofix Prompt"
    _order = "phase, version desc"
    _rec_name = "phase"
    _access_anchors = frozendict({"company": ""})

    phase = fields.Selection(
        selection=[
            ("diagnose", "Diagnose"),
            ("fix", "Fix"),
        ],
        required=True,
    )
    version = fields.Integer(
        required=True,
    )
    body = fields.Text(
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )

    _version_uniq = models.Constraint(
        "UNIQUE(phase, version)",
        "A phase's prompt versions are unique.",
    )

    @api.model
    def _current(self, phase: str) -> ErrorIncidentAutofixPrompt:
        return self.search([("phase", "=", phase)], order="version desc", limit=1)
