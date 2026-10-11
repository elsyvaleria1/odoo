from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    test_automation_employee = fields.Boolean()
