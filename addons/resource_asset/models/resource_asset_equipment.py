from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetEquipment(models.Model):
    _name = "resource.asset.equipment"
    _description = "Equipment"
    _inherit = ["resource.asset"]
    _table = "resource_asset_equipment"

    serial_number = ResourceIdentifier(identifier_code="serial", through="resource_id")
