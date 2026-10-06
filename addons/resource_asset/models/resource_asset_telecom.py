from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetTelecom(models.Model):
    _name = "resource.asset.telecom"
    _description = "Telecom"
    _inherit = ["resource.asset"]
    _table = "resource_asset_telecom"

    serial_number = ResourceIdentifier(identifier_code="serial", through="resource_id")
    imei = ResourceIdentifier(
        identifier_code="imei",
        through="resource_id",
        string="IMEI",
        help="International Mobile Equipment Identity of a cellular-capable asset.",
    )
