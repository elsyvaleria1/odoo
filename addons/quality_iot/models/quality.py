from odoo import fields, models


class QualityPoint(models.Model):
    _inherit = "quality.point"

    device_id = fields.Many2one(
        comodel_name="iot.device",
        index="btree_not_null",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )


class QualityCheck(models.Model):
    _inherit = "quality.check"

    ip = fields.Char(related="point_id.device_id.iot_id.ip")
    identifier = fields.Char(related="point_id.device_id.identifier")
    iot_box_id = fields.Many2one(
        related="point_id.device_id.iot_id",
        store=False,
    )
    device_name = fields.Char(
        related="point_id.device_id.name",
        string="Device Name: ",
    )
