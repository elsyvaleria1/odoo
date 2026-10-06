from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _get_default_settle_product(self):
        return (
            self.env.ref(
                "pos_settle_due.product_product_settle", raise_if_not_found=False
            )
            or self.env["product.product"]
        )

    def _get_default_deposit_product(self):
        return (
            self.env.ref(
                "pos_settle_due.product_product_deposit", raise_if_not_found=False
            )
            or self.env["product.product"]
        )

    def _get_default_settle_invoice_product(self):
        return (
            self.env.ref(
                "pos_settle_due.product_product_settle_invoice",
                raise_if_not_found=False,
            )
            or self.env["product.product"]
        )

    settle_due_product_id = fields.Many2one(
        comodel_name="product.product",
        default=lambda self: self._get_default_settle_product(),
        help="This product is used as to settle due of customer account.",
    )
    deposit_product_id = fields.Many2one(
        comodel_name="product.product",
        default=lambda self: self._get_default_deposit_product(),
        help="This product is used to deposit money on customer account.",
    )
    settle_invoice_product_id = fields.Many2one(
        comodel_name="product.product",
        default=lambda self: self._get_default_settle_invoice_product(),
        help="This product is used as to settle invoices of customer.",
    )

    @api.model
    def _update_settle_deposit_products_on_module_install(self) -> None:
        configs = self.env["pos.config"].search([])
        product_settle = self._get_default_settle_product()
        product_deposit = self._get_default_deposit_product()
        product_settle_inv = self._get_default_settle_invoice_product()
        for conf in configs:
            conf.settle_due_product_id = product_settle
            conf.deposit_product_id = product_deposit
            conf.settle_invoice_product_id = product_settle_inv

    def _get_special_products(self):
        return (
            super()._get_special_products()
            | self._get_default_settle_product()
            | self._get_default_deposit_product()
            | self._get_default_settle_invoice_product()
        )
