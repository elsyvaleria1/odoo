from odoo import fields, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    workcenter_id = fields.One2one(
        comodel_name="mrp.workcenter",
        inverse_name="asset_id",
        string="Work Center",
        context={"active_test": False},
    )
