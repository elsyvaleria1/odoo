from odoo import fields, models


class IotDevice(models.Model):
    _inherit = "iot.device"

    picking_type_ids = fields.Many2many(
        comodel_name="stock.picking.type",
        string="Operation Types",
        domain=[
            ("code", "!=", "mrp_operation"),
        ],
    )
