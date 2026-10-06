from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"
    _search_visibility_fields = ()
    _barcode_field = "barcode"

    has_image = fields.Boolean(compute="_compute_has_image")

    # `image_128` is what this reads, but depending on it buys nothing: core declares it as a
    # compute with no `depends` of its own (`_compute_variant_image`), so it is never a trigger.
    # The stored sources behind it are the variant's own image and, when the variant has none,
    # the template's — measured: with these two, writing `image_1920` flips `has_image` in the
    # same transaction; with `image_128` (or with the field itself, as it was) it does not.
    @api.depends("image_variant_128", "product_tmpl_id.image_128")
    def _compute_has_image(self) -> None:
        for product in self:
            product.has_image = bool(product.image_128)

    @api.model
    def _search(self, domain, *args, **kwargs):
        # sudo is added for external users to get the products
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
