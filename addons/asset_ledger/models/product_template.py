from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _create_missing_assets(self):
        assets = super()._create_missing_assets()
        assets.trace_id._sync_resource_asset()
        return assets
