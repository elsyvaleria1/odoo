from odoo import api, models


class ProductUom(models.Model):
    _inherit = "product.uom"
    _search_visibility_fields = ()
    _barcode_field = "barcode"

    @api.model
    def _search(self, domain, *args, **kwargs):
        # A packaging's barcode lives in the GS1 product AI space (see
        # `stock.picking.filter_on_barcode`), so a scanned `(01)` payload has to be unpadded
        # here the same way `product.product` unpads it. Every other barcode model in this
        # module carries this override; `product.uom` was the one that did not, and the GS1
        # unpadding for it happened by hand in the barcode controller instead — one model's
        # search behaviour implemented in a route.
        domain = self.env.company.sudo().barcodes_config_id.nomenclature_id._preprocess_gs1_search_args(
            domain, ["product"]
        )
        return super()._search(domain, *args, **kwargs)

    @api.model
    def _get_fields_stock_barcode(self):
        return [
            "barcode",
            "product_id",
            "uom_id",
        ]

    def _get_stock_barcode_specific_data(self) -> dict:
        return {
            "product.product": self.product_id.read(
                self.env["product.product"]._get_fields_stock_barcode(), load=False
            ),
            "uom.uom": self.uom_id.read(
                self.env["uom.uom"]._get_fields_stock_barcode(), load=False
            ),
        }
