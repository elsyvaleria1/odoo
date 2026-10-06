from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetMachinery(models.Model):
    _name = "resource.asset.machinery"
    _description = "Machinery"
    _inherit = ["resource.asset"]
    _table = "resource_asset_machinery"

    serial_number = ResourceIdentifier(identifier_code="serial", through="resource_id")
