from odoo import api, fields, models


class WalletCard(models.Model):
    _name = "wallet.card"
    _description = "Electronic Wallet Card"
    _inherit = ["mixin.mail.thread"]
    _order = "account_id, number, id"
    _check_company_auto = True

    # FIELDS
    # Core identification
    name = fields.Char(
        compute="_compute_name",
        precompute=True,
        store=True,
    )
    number = fields.Char(
        index=True,
        required=True,
        help="The number printed on the card or tag.",
    )
    account_id = fields.Many2one(
        comodel_name="wallet.account",
        index=True,
        required=True,
        ondelete="cascade",
    )
    kind = fields.Selection(
        related="account_id.kind",
    )
    company_id = fields.Many2one(
        related="account_id.company_id",
    )
    active = fields.Boolean(default=True)
    holder_id = fields.Many2one(
        comodel_name="res.partner",
        check_company=True,
        tracking=True,
        help="Who carries the card.",
    )
    note = fields.Text()
    # Balance block
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount_balance = fields.Monetary(
        compute="_compute_amount_balance",
        store=True,
        help="The latest balance snapshot.",
    )
    date_balance = fields.Datetime(
        compute="_compute_amount_balance",
        store=True,
    )
    amount_threshold_low = fields.Monetary(related="account_id.amount_threshold_low")
    is_low_balance = fields.Boolean(
        compute="_compute_is_low_balance",
        store=True,
        help="The latest balance is below the account's threshold.",
    )
    balance_ids = fields.One2many(
        comodel_name="wallet.balance",
        inverse_name="card_id",
    )
    # Transaction block
    transaction_ids = fields.One2many(
        comodel_name="wallet.transaction",
        inverse_name="card_id",
    )
    count_transaction = fields.Count(count_of="transaction_ids")
    amount_spent = fields.Monetary(compute="_compute_amount_spent")

    # CONSTRAINTS
    _number_account_uniq = models.Constraint(
        "UNIQUE(number, account_id)",
        "A card number must be unique per wallet account.",
    )

    # COMPUTE METHODS
    @api.depends("number", "account_id.name")
    def _compute_name(self):
        for card in self:
            card.name = f"{card.account_id.name or '?'} {card.number or ''}".strip()

    @api.depends("balance_ids.amount_balance", "balance_ids.date")
    def _compute_amount_balance(self) -> None:
        latest = self.env["wallet.balance"]._get_latest_by_card(self)
        for card in self:
            snapshot = latest.get(card.id)
            card.amount_balance = snapshot.amount_balance if snapshot else 0.0
            card.date_balance = snapshot.date if snapshot else False

    @api.depends("amount_balance", "date_balance", "account_id.amount_threshold_low")
    def _compute_is_low_balance(self) -> None:
        # a card never read has no balance yet, not a balance of zero
        for card in self:
            card.is_low_balance = bool(card.date_balance) and (
                card.amount_balance < card.amount_threshold_low
            )

    @api.depends("transaction_ids.amount")
    def _compute_amount_spent(self) -> None:
        groups = self.env["wallet.transaction"]._read_group(
            domain=[("card_id", "in", self.ids)],
            groupby=["card_id"],
            aggregates=["amount:sum"],
        )
        totals = {card.id: total for card, total in groups}
        for card in self:
            card.amount_spent = totals.get(card.id, 0.0)

    # ACTION METHODS
    def action_view_transactions(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Transactions"),
            "res_model": "wallet.transaction",
            "view_mode": "list,form",
            "domain": [("card_id", "=", self.id)],
            "context": {"default_card_id": self.id},
        }

    def action_view_balances(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Balance History"),
            "res_model": "wallet.balance",
            "view_mode": "list,graph",
            "domain": [("card_id", "=", self.id)],
            "context": {"default_card_id": self.id},
        }
