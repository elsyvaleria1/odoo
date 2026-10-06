from odoo import fields, models


class ErrorIncident(models.Model):
    _inherit = "error.incident"

    pull_ids = fields.One2many(
        comodel_name="integration.github.pull",
        inverse_name="incident_id",
        string="Pull Requests",
        readonly=True,
    )
