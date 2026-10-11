from typing import Any

from odoo import fields, models
from odoo.tools import frozendict

from .error_incident import SOURCES


class ErrorIncidentRule(models.Model):
    _name = "error.incident.rule"
    _description = "Error Incident Rule"
    _order = "sequence, id"
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        required=True,
    )
    sequence = fields.Integer(
        default=10,
    )
    active = fields.Boolean(
        default=True,
    )
    source = fields.Selection(
        selection=SOURCES,
        help="Only incidents first seen here. Empty: any.",
    )
    exception_type = fields.Char(
        help="Only this exception, as a traceback prints it "
        "(ValueError, psycopg.errors.UniqueViolation). Empty: any.",
    )
    origin_module = fields.Char(
        string="Module",
        help="Only incidents whose origin is in this module. Empty: any.",
    )
    incident_ids = fields.One2many(
        comodel_name="error.incident",
        inverse_name="rule_id",
        string="Incidents",
        readonly=True,
    )

    def _match(self, payload: dict[str, Any]) -> ErrorIncidentRule:
        for rule in self.search([]):
            if rule.source and rule.source != payload["source"]:
                continue
            if rule.exception_type and rule.exception_type != payload["exception_type"]:
                continue
            if rule.origin_module and rule.origin_module != payload["origin_module"]:
                continue
            return rule
        return self.browse()
