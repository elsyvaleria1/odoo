from odoo import fields, models


class MrpWorkcenter(models.Model):
    _name = "mrp.workcenter"
    _inherit = [
        "mrp.workcenter",
        "mixin.mail.thread",
        "mixin.mail.activity",
        "mixin.maintenance.target",
    ]

    asset_component_ids = fields.One2many(
        related="asset_id.child_ids",
        string="Tools and Components",
        readonly=False,
    )
