from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"
    _search_visibility_fields = ()
    _barcode_field = "barcode"

    has_image = fields.Boolean(compute="_compute_has_image")

    @api.depends("image_variant_128", "product_tmpl_id.image_128")
    def _compute_has_image(self) -> None:
        for product in self:
            product.has_image = bool(product.image_128)

    @api.model
    def _search(self, domain, *args, **kwargs):
        domain = self.env.company.sudo().barcodes_config_id.nomenclature_id._preprocess_gs1_search_args(
            domain, ["product"]
        )
        return super()._search(domain, *args, **kwargs)

    @api.model
    def _get_fields_stock_barcode(self):
        return [
            "barcode",
            "categ_id",
            "code",
            "default_code",
            "display_name",
            "has_image",
            "is_storable",
            "tracking",
            "uom_id",
        ]

    def _get_stock_barcode_specific_data(self) -> dict:
        return {
            "uom.uom": self.uom_id.read(
                self.env["uom.uom"]._get_fields_stock_barcode(), load=False
            )
        }
