from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetFurniture(models.Model):
    _name = "resource.asset.furniture"
    _description = "Furniture"
    _inherit = ["resource.asset"]
    _table = "resource_asset_furniture"

    inventory_tag = ResourceIdentifier(
        identifier_code="inventory", through="resource_id"
    )
