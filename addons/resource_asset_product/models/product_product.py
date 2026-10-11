from odoo import models


class ProductProduct(models.Model):

    _inherit = "product.product"

    def action_view_assets(self):
        self.check_singleton()
        return self.product_tmpl_id.action_view_assets()
