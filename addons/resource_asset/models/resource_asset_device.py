from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetDevice(models.Model):
    _name = "resource.asset.device"
    _description = "Device"
    _inherit = ["resource.asset"]
    _table = "resource_asset_device"

    serial_number = ResourceIdentifier(identifier_code="serial", through="resource_id")
    imei = ResourceIdentifier(
        identifier_code="imei",
        through="resource_id",
        string="IMEI",
        help="International Mobile Equipment Identity of a cellular-capable asset.",
    )
