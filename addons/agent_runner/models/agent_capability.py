from odoo import fields, models
from odoo.tools import frozendict


class AgentCapability(models.Model):
    _name = "agent.capability"
    _description = "Agent Capability"
    _order = "code"
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(
        required=True,
        help="What a runner names to claim work of this kind.",
    )

    _code_uniq = models.Constraint(
        "UNIQUE(code)",
        "A capability with this code already exists.",
    )
