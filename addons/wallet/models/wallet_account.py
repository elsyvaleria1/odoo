from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

from odoo.addons.base.models.res_partner import _selection_timezones

WALLET_KINDS = [
    ("fuel", "Fuel"),
    ("toll", "Toll"),
    ("other", "Other"),
]
PREPAID_ACCOUNT_TYPES = ("asset_prepayments", "asset_current", "asset_cash")
# a card read this long before its account's newest reading is behind: the
# issuer may have stopped reporting it (cancelled, replaced)
STALE_MARGIN = timedelta(days=1)


class WalletAccount(models.Model):
    _name = "wallet.account"
    _description = "Electronic Wallet Account"
    _inherit = ["mixin.mail.thread"]
    _order = "kind, name, id"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    # FIELDS
    # Core identification
    name = fields.Char(
        required=True,
        tracking=True,
    )
    kind = fields.Selection(
        selection=WALLET_KINDS,
        default="fuel",
        required=True,
        tracking=True,
        help="What the wallet pays for. Cards inherit it.",
    )
    active = fields.Boolean(default=True)
    issuer_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
        check_company=True,
        tracking=True,
        help="Who holds the prepaid balance and issued the cards.",
    )
    reference = fields.Char(
        help="The issuer's own identifier of this account (client, contract, "
        "consignee)."
    )
    tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        default=lambda self: self._default_tz(),
        required=True,
        help="The time zone the issuer reports its times in, and the one a "
        "transaction is dated in.",
    )
    note = fields.Text()
    # Financial block
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Prepaid Account",
        domain="[('account_type', 'in', ('asset_prepayments', 'asset_current',"
        " 'asset_cash'))]",
        check_company=True,
        tracking=True,
        help="The asset account of the chart that carries the balance held "
        "with the issuer.",
    )
    amount_threshold_low = fields.Monetary(
        default=500.0,
        help="A card whose balance falls below this is flagged.",
    )
    amount_balance = fields.Monetary(
        compute="_compute_amount_balance",
        aggregator="sum",
        help="Sum of the cards' latest balances.",
    )
    date_balance = fields.Datetime(
        string="Balance As Of",
        compute="_compute_balance_freshness",
        help="The newest of the active cards' latest readings.",
    )
    count_card_unread = fields.Integer(
        string="Cards Never Read",
        compute="_compute_balance_freshness",
        help="Active cards with no balance reading yet: their balance is unknown, "
        "not zero.",
    )
    count_card_stale = fields.Integer(
        string="Cards Behind",
        compute="_compute_balance_freshness",
        help="Active cards last read more than a day before the newest reading: "
        "the issuer may no longer report them, and their balance is that old.",
    )
    # Card block
    card_ids = fields.One2many(
        comodel_name="wallet.card",
        inverse_name="account_id",
    )
    count_card = fields.Count(count_of="card_ids")
    count_card_low = fields.Integer(compute="_compute_count_card_low")

    # CONSTRAINTS
    _name_company_uniq = models.Constraint(
        "UNIQUE(company_id, name)",
        "A wallet account's name must be unique per company.",
    )

    # CRUD METHODS
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "account_id" not in vals:
                company_id = vals.get("company_id") or self.env.company.id
                vals["account_id"] = self._get_default_prepaid_account(company_id).id
        return super().create(vals_list)

    # CONSTRAINT METHODS
    @api.constrains("account_id")
    def _check_account_is_prepaid(self) -> None:
        for account in self.filtered("account_id"):
            if account.account_id.account_type not in PREPAID_ACCOUNT_TYPES:
                raise ValidationError(
                    self.env._(
                        "Wallet %(wallet)s: %(account)s is a %(type)s account; a "
                        "prepaid balance sits on a prepayment, current-asset or "
                        "cash account.",
                        wallet=account.name,
                        account=account.account_id.display_name,
                        type=dict(
                            account.account_id._fields["account_type"].selection
                        ).get(account.account_id.account_type),
                    )
                )

    # COMPUTE METHODS
    @api.depends("card_ids.amount_balance", "card_ids.active")
    def _compute_amount_balance(self) -> None:
        self.check_access("read")
        groups = self.env["wallet.card"]._read_group(
            domain=[("account_id", "in", self.ids)],
            groupby=["account_id"],
            aggregates=["amount_balance:sum"],
        )
        totals = {account.id: total for account, total in groups}
        for account in self:
            account.amount_balance = totals.get(account.id, 0.0)

    @api.depends("card_ids.date_balance", "card_ids.active")
    def _compute_balance_freshness(self) -> None:
        for account in self:
            newest, _read, unread, stale = account._split_cards_by_reading()
            account.date_balance = newest or False
            account.count_card_unread = len(unread)
            account.count_card_stale = len(stale)

    @api.depends("card_ids.is_low_balance", "card_ids.active")
    def _compute_count_card_low(self) -> None:
        groups = self.env["wallet.card"]._read_group(
            domain=[("account_id", "in", self.ids), ("is_low_balance", "=", True)],
            groupby=["account_id"],
            aggregates=["__count"],
        )
        counts = {account.id: count for account, count in groups}
        for account in self:
            account.count_card_low = counts.get(account.id, 0)

    # ACTION METHODS
    def action_view_cards(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Cards"),
            "res_model": "wallet.card",
            "view_mode": "list,kanban,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    # BUSINESS METHODS
    def _get_balance_summary(self, with_cards=False) -> list[dict]:
        """Each account's balance as far as its readings support it, for a
        caller that words it (a bot, a digest).

        :param bool with_cards: also list the active cards, the read ones by
            balance, highest first, then those never read
        :return: per account, in the order of ``self``: ``account``,
            ``amount_balance`` (of the cards read), ``date_balance`` (the newest
            reading, UTC, None when no card was read), ``count_card``,
            ``count_card_low``, ``cards_unread`` and ``cards_stale``
            (wallet.card recordsets) and, with ``with_cards``, ``cards``
        :rtype: list[dict]
        """
        summary = []
        for account in self:
            newest, read, unread, stale = account._split_cards_by_reading()
            # only read cards add up: one never read is counted apart, not as
            # zero, even when an old import left it an amount with no reading
            row = {
                "account": account,
                "amount_balance": account.currency_id.round(
                    sum(read.mapped("amount_balance"))
                ),
                "date_balance": newest,
                "count_card": len(account.card_ids),
                "count_card_low": account.count_card_low,
                "cards_unread": unread,
                "cards_stale": stale,
            }
            if with_cards:
                row["cards"] = read.sorted("amount_balance", reverse=True) + unread
            summary.append(row)
        return summary

    # HELPER METHODS
    def _split_cards_by_reading(self) -> tuple:
        """The account's active cards by reading: the newest reading (None if
        none), the cards read, those never read and those read more than
        ``STALE_MARGIN`` before the newest."""
        self.check_singleton()
        read = self.card_ids.filtered("date_balance")
        newest = max(read.mapped("date_balance"), default=None)
        stale = read.filtered(lambda card: card.date_balance < newest - STALE_MARGIN)
        return newest, read, self.card_ids - read, stale

    def _default_tz(self):
        return self.env.company.partner_id.tz or self.env.user.tz or "UTC"

    @api.model
    def _get_default_prepaid_account(self, company_id):
        return self.env["account.account"].search(
            [
                ("account_type", "=", "asset_prepayments"),
                ("company_ids", "in", company_id),
            ],
            limit=1,
        )
