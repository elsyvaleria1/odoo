from odoo import fields, models
from odoo.tools import frozendict


# A rolling report's "rebuild in full" flag is operational state written from
# business flows (a company created, a tracker re-pointed), so it does not live
# in ir.config_parameter: creating or rewriting a parameter clears the
# registry's "stable" caches in every worker.
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
