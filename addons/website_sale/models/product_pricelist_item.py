from odoo import api, models
from odoo.fields import Domain


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    @api.model
    def _access_predicate_website_offered(self, bind, args) -> Domain:
        # the items of the pricelists a shop visitor may price with
        return Domain(
            "pricelist_id",
            "any",
            self.env["product.pricelist"]._access_predicate_website_offered(bind, args),
        )

    def _show_discount_on_shop(self):
        if not self:
            return False

        self.check_singleton()

        return self.compute_price == "percentage" or (
            self.compute_price == "formula"
            and self.price_discount
            and self.base in ("list_price", "pricelist")
        )
