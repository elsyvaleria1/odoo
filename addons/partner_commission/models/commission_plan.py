from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommissionPlan(models.Model):
    _name = "commission.plan"
    _description = "Commission plan"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Purchase Default Product",
        default=lambda self: self.env.ref("partner_commission.product_commission"),
        required=True,
        domain=[("purchase_ok", "=", True)],
    )
    commission_rule_ids = fields.One2many(
        comodel_name="commission.rule",
        inverse_name="plan_id",
        string="Rules",
        copy=True,
    )
    company_id = fields.Many2one(comodel_name="res.company")

    def _match_rules(self, product, template, pricelist):
        self.check_singleton()
        ancestor_ids = list(product.categ_id._get_ancestor_ids(include_self=True))
        rules = self.env["commission.rule"].search(
            [
                ("plan_id", "=", self.id),
                ("category_id", "in", ancestor_ids),
                "|",
                ("product_id", "=", product.id),
                ("product_id", "=", False),
                "|",
                ("template_id", "=", template),
                ("template_id", "=", False),
                "|",
                ("pricelist_id", "=", pricelist),
                ("pricelist_id", "=", False),
            ],
            order="sequence",
        )

        rules_by_category_id = rules.grouped(lambda r: r.category_id.id)
        for cat_id in reversed(ancestor_ids):
            if rule := rules_by_category_id.get(cat_id):
                return rule[0]
        return self.env["commission.rule"]


class CommissionRule(models.Model):
    _name = "commission.rule"
    _description = "Commission rules management."

    plan_id = fields.Many2one(
        comodel_name="commission.plan",
        string="Commission Plan",
        index=True,
        required=True,
        ondelete="cascade",
    )
    category_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        ondelete="cascade",
        help="If set, the rule does not apply to the whole category but only on the given product.\n"
        "The product must belong to the selected category.\n"
        "Use several rules if you need to match multiple products within a category.",
    )
    template_id = fields.Many2one(
        comodel_name="sale.order.template",
        string="Sale Order Template",
        ondelete="cascade",
    )
    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        ondelete="cascade",
    )
    rate = fields.Float(
        default=0,
        required=True,
    )
    is_capped = fields.Boolean(
        string="Capped",
        default=False,
        required=True,
        help="Whether the commission is capped.",
    )
    max_commission = fields.Float(
        help="Maximum amount, specified in the currency of the pricelist, if given."
    )
    sequence = fields.Integer()

    _check_rate = models.Constraint(
        "CHECK(rate >= 0 AND rate <= 100)",
        "Rate should be between 0 and 100.",
    )
    _check_combination_unique_index = models.UniqueIndex(
        "(plan_id, category_id, COALESCE(product_id, -1), COALESCE(template_id, -1), COALESCE(pricelist_id, -1))"
    )

    @api.constrains("product_id", "category_id")
    def _check_product_category(self) -> None:
        for rule in self:
            if rule.product_id and rule.product_id.categ_id != rule.category_id:
                raise ValidationError(
                    self.env._(
                        "Product %(product)s does not belong to category %(category)s",
                        product=rule.product_id.code,
                        category=rule.category_id.name,
                    )
                )

    @api.onchange("is_capped")
    def _onchange_is_capped(self) -> None:
        if not self.is_capped:
            self.max_commission = 0
