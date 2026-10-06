from odoo import models

from odoo.addons.resource.fields import ResourceIdentifier


class ResourceAssetProperty(models.Model):
    _name = "resource.asset.property"
    _description = "Property"
    _inherit = ["resource.asset"]
    _table = "resource_asset_property"

    cadastral_id = ResourceIdentifier(
        identifier_code="cadastral",
        through="resource_id",
        string="Cadastral ID",
        help="Government-assigned parcel identifier for real estate assets.",
    )
