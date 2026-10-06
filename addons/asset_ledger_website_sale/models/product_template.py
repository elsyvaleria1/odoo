import re
from urllib.parse import quote

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    website_quote_only = fields.Boolean(
        string="Quote via WhatsApp",
        help="Replace the eCommerce add-to-cart button with a WhatsApp quote "
        "button on this product's website page. Used for catalog-only items "
        "such as vehicles that are not sold online.",
    )

    def _sync_quote_only_stock_policy(self) -> None:
        if "allow_out_of_stock_order" in self._fields:
            quote_only = self.filtered("website_quote_only")
            if quote_only:
                quote_only.allow_out_of_stock_order = True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_quote_only_stock_policy()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("website_quote_only"):
            self._sync_quote_only_stock_policy()
        return res

    def _get_whatsapp_quote_url(self, website) -> str:
        self.check_singleton()
        number = re.sub(r"\D", "", website.whatsapp_sales_number or "")
        if not number:
            return ""
        product_url = website.get_base_url() + (self.website_url or "")
        message = self.env._(
            "Hola, me interesa el vehículo %(name)s: %(url)s",
            name=self.name,
            url=product_url,
        )
        return "https://wa.me/%s?text=%s" % (number, quote(message))
