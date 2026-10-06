from odoo import fields, models
from odoo.tools import frozendict


class DeviceWeekday(models.Model):
    _name = "device.weekday"
    _access_anchors = frozendict({"company": ""})
    _description = "Day of the Week"
    _order = "sequence"
    _rec_name = "name"

    name = fields.Char(
        translate=True,
        required=True,
        help="Day name (e.g. Monday)",
    )
    code = fields.Char(
        required=True,
        help="Numeric code matching Python datetime.weekday() (0=Monday, 6=Sunday)",
    )
    sequence = fields.Integer(
        default=0,
        help="Display order (0=Monday, 6=Sunday)",
    )
