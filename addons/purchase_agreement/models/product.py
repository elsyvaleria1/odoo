from odoo import fields, models


class ProductSupplierinfo(models.Model):
    _inherit = "product.supplierinfo"

    agreement_id = fields.Many2one(
        comodel_name="purchase.agreement",
        related="agreement_line_id.agreement_id",
        string="Agreement",
    )
    agreement_line_id = fields.Many2one(
        comodel_name="purchase.agreement.line",
        index="btree_not_null",
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _prepare_sellers(self, params=False):
        sellers = super()._prepare_sellers(params=params)
        if (
            params
            and params.get("order_id")
            and params["order_id"]._fields.get("agreement_id")
        ):
            return sellers.filtered(
                lambda s: (
                    not s.agreement_id
                    or s.agreement_id == params["order_id"].agreement_id
                )
            )
        else:
            return sellers
