from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    appointment_type_id = fields.Many2one(comodel_name="appointment.type")

    @api.depends("appointment_type_id")
    def _compute_last_data_change(self) -> None:
        super()._compute_last_data_change()
