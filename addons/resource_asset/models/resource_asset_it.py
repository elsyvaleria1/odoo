from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetIt(models.Model):
    _name = "resource.asset.it"
    _description = "IT Equipment"
    _inherit = ["resource.asset"]
    _table = "resource_asset_it"

    serial_number = ResourceIdentifier(identifier_code="serial", through="resource_id")
