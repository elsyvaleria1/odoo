from odoo import fields, models


class DeviceDeviceCategory(models.Model):
    _inherit = "device.kind"

    comm_protocol = fields.Selection(
        selection_add=[
            ("modbus_tcp", "Modbus TCP"),
            ("modbus_rtu", "Modbus RTU"),
        ],
        ondelete={"modbus_tcp": "set null", "modbus_rtu": "set null"},
    )
