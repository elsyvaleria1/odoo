from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _restore_lazada_data_product(self, default_name, default_type, xmlid):
        product = (
            self.env["product.product"]
            .with_context(mail_create_nosubscribe=True)
            .create(
                {
                    "name": default_name,
                    "type": default_type,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                }
            )
        )
        product._configure_for_lazada()
        ir_model = self.env["ir.model.data"].search(
            [
                ("module", "=", "sale_lazada"),
                ("name", "=", xmlid),
            ]
        )
        if not ir_model:
            self.env["ir.model.data"].create(
                {
                    "module": "sale_lazada",
                    "name": xmlid,
                    "model": "product.product",
                    "res_id": product.id,
                }
            )
        else:
            ir_model.write({"res_id": product.id})
        return product

    def _configure_for_lazada(self) -> None:
        for product_template in self.product_tmpl_id:
            product_template.write(
                {
                    "active": False,
                    "invoice_policy": "ordered"
                    if product_template.type == "service"
                    else "transferred",
                }
            )
