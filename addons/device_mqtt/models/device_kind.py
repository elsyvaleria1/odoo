from odoo import fields, models


class DeviceDeviceCategory(models.Model):
    _inherit = "device.kind"

    comm_protocol = fields.Selection(
        selection_add=[("mqtt", "MQTT")],
        ondelete={"mqtt": "set null"},
    )
