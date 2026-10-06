from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class WalletReorderRule(models.Model):
    _name = "wallet.reorder.rule"
    _description = "Electronic Wallet Reordering Rule"
    _order = "account_id, card_id, id"
    _check_company_auto = True

    # FIELDS
    # Core identification
    name = fields.Char(
        compute="_compute_name",
        precompute=True,
        store=True,
    )
    card_id = fields.Many2one(
        comodel_name="wallet.card",
        index=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(  # noqa: E8529  One2many inverse of wallet.account.reorder_rule_ids
        related="card_id.account_id",
        precompute=True,
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="card_id.company_id",
    )
    active = fields.Boolean(default=True)
    # Rule block
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount_min = fields.Monetary(
        required=True,
        help="Below this balance the card is topped up.",
    )
    amount_max = fields.Monetary(
        required=True,
        help="The balance a top-up brings the card back to.",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Top-up Product",
        compute="_compute_product_id",
        store=True,
        readonly=False,
        check_company=True,
    )
    # Balance block
    amount_balance = fields.Monetary(related="card_id.amount_balance")
    date_balance = fields.Datetime(related="card_id.date_balance")
    amount_to_reload = fields.Monetary(
        compute="_compute_amount_to_reload",
        store=True,
        help="What brings the card back to its maximum, once it is under its minimum.",
    )
    # Purchase block
    purchase_line_ids = fields.One2many(
        comodel_name="purchase.order.line",
        inverse_name="wallet_reorder_rule_id",
    )
    open_purchase_line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        compute="_compute_open_purchase_line_id",
        help="The top-up ordered and not yet seen on a balance snapshot.",
    )
    state = fields.Selection(
        selection=[
            ("ok", "Above Minimum"),
            ("reorder", "To Reload"),
            ("ordered", "Reload Ordered"),
        ],
        compute="_compute_state",
        search="_search_state",
    )

    # CONSTRAINTS
    _card_uniq = models.Constraint(
        "UNIQUE(card_id)",
        "A card has one reordering rule.",
    )

    # CONSTRAINT METHODS
    @api.constrains("amount_min", "amount_max")
    def _check_amounts(self) -> None:
        for rule in self:
            if rule.amount_max < rule.amount_min or rule.amount_min < 0:
                raise ValidationError(
                    self.env._(
                        "%(rule)s: the maximum must be at least the minimum, and "
                        "the minimum cannot be negative.",
                        rule=rule.name,
                    )
                )

    # COMPUTE METHODS
    @api.depends("card_id.name")
    def _compute_name(self):
        for rule in self:
            rule.name = rule.card_id.name or "?"

    @api.depends("card_id.account_id.reload_product_id")
    def _compute_product_id(self) -> None:
        for rule in self.filtered(lambda r: not r.product_id):
            rule.product_id = rule.card_id.account_id.reload_product_id

    @api.depends("card_id.amount_balance", "amount_min", "amount_max")
    def _compute_amount_to_reload(self) -> None:
        for rule in self:
            balance = rule.card_id.amount_balance
            rule.amount_to_reload = (
                max(0.0, rule.amount_max - balance)
                if balance < rule.amount_min
                else 0.0
            )

    @api.depends(
        "purchase_line_ids.order_id.state",
        "purchase_line_ids.create_date",
        "card_id.date_balance",
    )
    def _compute_open_purchase_line_id(self) -> None:
        for rule in self:
            rule.open_purchase_line_id = rule._get_open_purchase_line()

    @api.depends("amount_to_reload", "open_purchase_line_id")
    def _compute_state(self):
        for rule in self:
            if rule.open_purchase_line_id:
                rule.state = "ordered"
            elif rule.amount_to_reload:
                rule.state = "reorder"
            else:
                rule.state = "ok"

    # SEARCH METHODS
    def _search_state(self, operator, value):
        if operator not in ("=", "in"):
            return NotImplemented
        wanted = {value} if isinstance(value, str) else set(value)
        rules = self.search([]).filtered(lambda rule: rule.state in wanted)
        return [("id", "in", rules.ids)]

    # ACTION METHODS
    def action_procure(self) -> dict | None:
        orders = self._procure()
        if not orders:
            return None
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Wallet Top-ups"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
        }

    # PROCUREMENT METHODS
    @api.model
    def _cron_procure(self):
        return self.search([])._procure()

    def _procure(self):
        """One draft purchase order per account and company for the rules
        under their minimum with no top-up ordered yet."""
        Order = self.env["purchase.order"]
        orders = Order.browse()
        by_account = {}
        for rule in self:
            if not rule.amount_to_reload or rule._get_open_purchase_line():
                continue
            if not rule.product_id:
                raise ValidationError(
                    self.env._(
                        "%(rule)s has no top-up product; set one on the rule or on "
                        "its wallet account.",
                        rule=rule.name,
                    )
                )
            by_account.setdefault((rule.account_id, rule.company_id), []).append(rule)
        for (account, company), rules in by_account.items():
            order = Order.with_company(company).create(
                {
                    "partner_id": account.issuer_id.id,
                    "company_id": company.id,
                    "origin": account.name,
                    "line_ids": [
                        Command.create(rule._prepare_purchase_line_vals())
                        for rule in rules
                    ],
                }
            )
            orders |= order
        return orders

    def _get_open_purchase_line(self):
        self.check_singleton()
        lines = self.purchase_line_ids.filtered(
            lambda line: (
                line.order_id.state == "draft"
                or (
                    line.order_id.state == "done"
                    and (
                        not self.card_id.date_balance
                        or line.create_date > self.card_id.date_balance
                    )
                )
            )
        )
        return lines[:1]

    # HELPER METHODS
    def _prepare_purchase_line_vals(self) -> dict:
        self.check_singleton()
        return {
            "product_id": self.product_id.id,
            "name": self.env._(
                "Top-up %(card)s to %(amount)s",
                card=self.card_id.name,
                amount=self.amount_max,
            ),
            "product_qty": 1.0,
            "price_unit": self.amount_to_reload,
            "wallet_reorder_rule_id": self.id,
        }
