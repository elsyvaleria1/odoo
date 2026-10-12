from odoo import api, fields, models


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    plan_id = fields.Many2one(
        comodel_name="sale.subscription.plan",
        string="Recurring Plan",
        index=True,
        check_company=True,
    )

    @api.depends("plan_id")
    def _compute_company_id(self):
        rules_with_pricelist = self.filtered("pricelist_id")
        super(ProductPricelistItem, rules_with_pricelist)._compute_company_id()
        for item in self - rules_with_pricelist:
            if not item.plan_id:
                continue
            item.company_id = item.plan_id.company_id

    @api.depends("plan_id")
    def _compute_is_pricelist_required(self) -> None:
        rules_with_plan = self.filtered("plan_id")
        super(
            ProductPricelistItem, self - rules_with_plan
        )._compute_is_pricelist_required()
        rules_with_plan.is_pricelist_required = False

    @api.depends("plan_id")
    def _compute_price(self) -> None:
        super()._compute_price()
        for item in self:
            if item.plan_id and item.compute_price in ("fixed", "percentage"):
                item.price = item.env._(
                    "%(price_details)s %(recurrence)s",
                    price_details=item.price,
                    recurrence=item.plan_id.sudo().billing_period_display_sentence,
                )

    def _is_applicable_for(self, product, qty_in_product_uom):
        if self.plan_id and not product.recurring_invoice:
            return False
        if (
            not self.plan_id
            and product.recurring_invoice
            and not product.allow_one_time_sale
        ):
            return False
        return super()._is_applicable_for(product, qty_in_product_uom)

    def _get_base_price(
        self, product, quantity, uom, date, currency, *, plan_id=None, **kwargs
    ):
        rule_base = self.base or "list_price"
        if rule_base == "list_price" and product.recurring_invoice and plan_id:
            domain = self.env["product.pricelist"]._get_domain_applicable_rules(
                products=product,
                date=fields.Datetime.now(),
                plan_id=plan_id,
            )
            no_pl_rule = self.env["product.pricelist.item"].search(
                domain, order="plan_id", limit=1
            )
            if no_pl_rule:
                return no_pl_rule._get_price(
                    product,
                    quantity,
                    uom,
                    date,
                    currency,
                    plan_id=plan_id,
                    **kwargs,
                )
        return super()._get_base_price(
            product, quantity, uom, date, currency, plan_id=plan_id, **kwargs
        )

    def _get_recurring_rules_order(self) -> str:
        return f"pricelist_id, plan_id, {self._order}"
