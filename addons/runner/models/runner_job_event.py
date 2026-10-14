from odoo import fields, models
from odoo.tools import frozendict


class RunnerJobEvent(models.Model):
    _name = "runner.job.event"
    _description = "Runner Job Event"
    _order = "id"
    _log_access = False
    _access_anchors = frozendict({"company": "job_id.company_id"})

    job_id = fields.Many2one(
        comodel_name="runner.job",
        string="Job",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    date_event = fields.Datetime(
        string="Date",
        default=fields.Datetime.now,
        readonly=True,
        required=True,
    )
    event_type = fields.Selection(
        selection=[
            ("info", "Info"),
            ("progress", "Progress"),
            ("warning", "Warning"),
            ("error", "Error"),
            ("system", "System"),
        ],
        string="Type",
        default="info",
        readonly=True,
        required=True,
    )
    message = fields.Text(
        readonly=True,
    )
    data = fields.Json(
        readonly=True,
    )
