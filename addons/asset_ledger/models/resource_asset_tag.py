from odoo import models


class ResourceAssetTag(models.Model):
    _name = "resource.tag"
    _description = "Asset Tag"
    _inherit = ["mixin.tag"]
