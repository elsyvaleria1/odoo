import ast
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class LoyaltyRule(models.Model):
    _name = "loyalty.rule"
    _description = "Loyalty Rule"

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        program_type = self.env.context.get("program_type")
        if program_type:
            defaults = self.env["loyalty.program"]._get_child_default_values(
                program_type, "rule_ids"
            )
            result.update({k: v for k, v in defaults.items() if k in fields})
        return result

    def _selection_reward_point_modes(self) -> list:
        symbol = self.env.context.get(
            "currency_symbol", self.env.company.currency_id.symbol
        )
        return [
            ("order", self.env._("per order")),
            ("money", self.env._("per %s spent", symbol)),
            ("unit", self.env._("per unit paid")),
        ]

    active = fields.Boolean(default=True)
    program_id = fields.Many2one(
        comodel_name="loyalty.program",
        index=True,
        required=True,
        ondelete="cascade",
    )
    program_type = fields.Selection(related="program_id.program_type")
    company_id = fields.Many2one(
        related="program_id.company_id",
    )
    currency_id = fields.Many2one(related="program_id.currency_id")

    user_has_debug = fields.Boolean(compute="_compute_user_has_debug")
    product_domain = fields.Char(default="[]")

    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Products",
    )
    product_category_id = fields.Many2one(
        comodel_name="product.category",
        string="Categories",
    )
    product_tag_id = fields.Many2one(comodel_name="product.tag")

    reward_point_amount = fields.Float(
        string="Reward",
        default=1,
    )
    reward_point_split = fields.Boolean(
        string="Split per unit",
        default=False,
        help="Whether to separate reward coupons per matched unit, only applies to 'future' programs and trigger mode per money spent or unit paid...",
    )
    reward_point_name = fields.Char(
        related="program_id.portal_point_name",
        readonly=True,
    )
    reward_point_mode = fields.Selection(
        selection=_selection_reward_point_modes,
        default="order",
        required=True,
    )

    minimum_qty = fields.Integer(
        string="Minimum Quantity",
        default=1,
    )
    minimum_amount = fields.Monetary(string="Minimum Purchase")
    minimum_amount_tax_mode = fields.Selection(
        selection=[
            ("incl", "tax included"),
            ("excl", "tax excluded"),
        ],
        default="incl",
        required=True,
    )

    mode = fields.Selection(
        selection=[
            ("auto", "Automatic"),
            ("with_code", "With a promotion code"),
        ],
        string="Application",
        compute="_compute_mode",
        store=True,
        readonly=False,
    )
    code = fields.Char(
        string="Discount code",
        compute="_compute_code",
        store=True,
        readonly=False,
    )

    _reward_point_amount_positive = models.Constraint(
        "CHECK (reward_point_amount > 0)",
        "Rule points reward must be strictly positive.",
    )

    @api.constrains("reward_point_split")
    def _check_reward_point_split(self) -> None:
        for rule in self:
            if rule.reward_point_split and (
                rule.program_id.applies_on == "both"
                or rule.program_id.program_type == "ewallet"
            ):
                raise ValidationError(
                    self.env._(
                        "Split per unit is not allowed for Loyalty and eWallet programs."
                    )
                )

    @api.constrains("code", "active")
    def _check_code(self) -> None:
        mapped_codes = self.filtered(lambda r: r.code and r.active).mapped("code")
        if len(mapped_codes) != len(set(mapped_codes)) or self.env[
            "loyalty.rule"
        ].search_count(
            [
                ("mode", "=", "with_code"),
                ("code", "in", mapped_codes),
                ("id", "not in", self.ids),
                ("active", "=", True),
            ],
            limit=1,
        ):
            raise ValidationError(self.env._("The promo code must be unique."))
        if self.env["loyalty.card"].search_count(
            [("code", "in", mapped_codes), ("active", "=", True)], limit=1
        ):
            raise ValidationError(self.env._("A coupon with the same code was found."))

    @api.model
    def _generate_code(self):
        return f"PROMO_CODE_{uuid4().hex[:8].upper()}"

    @api.depends("mode")
    def _compute_code(self) -> None:
        for rule in self:
            if rule.mode == "auto":
                rule.code = False
            elif rule.mode == "with_code" and not rule.code:
                rule.code = rule._generate_code()

    @api.depends("code")
    def _compute_mode(self) -> None:
        for rule in self:
            if rule.code:
                rule.mode = "with_code"
            else:
                rule.mode = "auto"

    @api.depends_context("uid")
    def _compute_user_has_debug(self) -> None:
        self.user_has_debug = self.env.user.has_group("base.group_no_one")

    def _get_domain_valid_product(self):
        self.check_singleton()
        constrains = []
        if self.product_ids:
            constrains.append([("id", "in", self.product_ids.ids)])
        if self.product_category_id:
            constrains.append([("categ_id", "child_of", self.product_category_id.id)])
        if self.product_tag_id:
            constrains.append([("all_product_tag_ids", "in", self.product_tag_id.id)])
        domain = Domain.OR(constrains) if constrains else Domain.TRUE
        if self.product_domain and self.product_domain != "[]":
            domain &= Domain(ast.literal_eval(self.product_domain))
        return domain

    def _get_valid_products(self):
        self.check_singleton()
        return self.env["product.product"].search(self._get_domain_valid_product())

    def _get_minimum_amount(self, currency_to):
        self.check_singleton()
        return self.currency_id._convert(
            self.minimum_amount,
            currency_to,
            self.company_id or self.env.company,
            fields.Date.today(),
        )
