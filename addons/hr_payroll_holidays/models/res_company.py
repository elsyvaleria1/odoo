from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    deferred_time_off_manager = fields.Many2one(comodel_name="res.users")
