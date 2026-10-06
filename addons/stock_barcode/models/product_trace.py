from odoo import api, models


class ProductTrace(models.Model):
    _inherit = "product.trace"
    _search_visibility_fields = ()
    _barcode_field = "name"

    @api.model
    def _search(self, domain, *args, **kwargs):
        # sudo is added for external users to get the lots
        domain = self.env.company.sudo().barcodes_config_id.nomenclature_id._preprocess_gs1_search_args(
            domain, ["lot"], field="name"
        )
        return super()._search(domain, *args, **kwargs)

    def _get_stock_barcode_specific_data(self) -> dict:
        products = self.product_id
        return {
            "product.product": products.read(
                self.env["product.product"]._get_fields_stock_barcode(), load=False
            ),
            "uom.uom": products.uom_id.read(
                self.env["uom.uom"]._get_fields_stock_barcode(), load=False
            ),
        }

    @api.model
    def _get_fields_stock_barcode(self):
        return ["name", "ref", "product_id"]
