from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    subscription_rule_ids = fields.One2many(
        comodel_name="product.pricelist.item",
        inverse_name="product_id",
        string="Subscription Pricings",
        compute="_compute_subscription_rule_ids",
        readonly=False,
    )

    @api.depends("product_tmpl_id")
    def _compute_subscription_rule_ids(self) -> None:
        for product in self:
            if not product.id:
                product.subscription_rule_ids = False
                continue
            product.subscription_rule_ids = (
                product.product_tmpl_id.subscription_rule_ids.filtered_domain(
                    ["|", ("product_id", "=", False), ("product_id", "=", product.id)]
                )
            )
