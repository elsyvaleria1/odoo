from odoo import fields, models
from odoo.tools import frozendict


class ReportRollingState(models.Model):
    _name = "report.rolling.state"
    _description = "Rolling Report State"
    _rec_name = "model"
    _log_access = False
    _access_anchors = frozendict({"company": ""})

    model = fields.Char(
        readonly=True,
        required=True,
    )
    stale = fields.Boolean(readonly=True)

    _model_unique = models.Constraint(
        "UNIQUE(model)", "A rolling report has one state row."
    )
