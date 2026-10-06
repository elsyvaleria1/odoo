from odoo import api, fields, models


class DeviceConfig(models.Model):
    _inherit = "device.profile"

    protocol = fields.Selection(
        selection_add=[
            ("modbus_tcp", "Modbus TCP"),
            ("modbus_rtu", "Modbus RTU"),
        ],
        ondelete={"modbus_tcp": "set default", "modbus_rtu": "set default"},
    )

    modbus_unit_id = fields.Integer(
        default=1,
        help="Modbus slave/unit identifier",
    )
    modbus_register_type = fields.Selection(
        selection=[
            ("holding", "Holding Registers"),
            ("input", "Input Registers"),
            ("coil", "Coils"),
            ("discrete", "Discrete Inputs"),
        ],
        default="holding",
        help="Type of Modbus registers to read",
    )

    @api.model
    def _stream_fields(self):
        return super()._stream_fields() | {"modbus_unit_id", "modbus_register_type"}
