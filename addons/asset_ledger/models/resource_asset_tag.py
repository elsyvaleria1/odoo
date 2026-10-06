from odoo import models


class ResourceAssetTag(models.Model):
    _name = "resource.asset.tag"
    _description = "Asset Tag"
    # `name`, `active`, `color` and the unique `code` come from the mixin.
    _inherit = ["mixin.tag"]
