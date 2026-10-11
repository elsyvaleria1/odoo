from datetime import UTC
from zoneinfo import ZoneInfo

from odoo import api, fields, models


class WalletTransaction(models.Model):
    _name = "wallet.transaction"
    _description = "Electronic Wallet Transaction"
    _order = "date_transaction desc, id desc"

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
    account_id = fields.Many2one(
        related="card_id.account_id",
        precompute=True,
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="card_id.company_id",
    )
    kind = fields.Selection(
        related="card_id.kind",
    )
    statement_id = fields.Many2one(
        comodel_name="wallet.statement",
        index=True,
        ondelete="set null",
    )
    external_ref = fields.Char(
        index=True,
        help="The issuer's own identifier of the transaction.",
    )
    date_transaction = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    date = fields.Date(
        compute="_compute_date",
        precompute=True,
        store=True,
    )
    place = fields.Char(help="Where it was paid: the station, the toll plaza.")
    place_code = fields.Char()
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        check_company=True,
        help="The merchant the issuer paid, when it is known as a partner.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount = fields.Monetary(
        required=True,
        help="What left the wallet: positive for a purchase, negative for a top-up "
        "or a refund.",
    )
    quantity = fields.Float(
        digits="Product Unit of Measure",
        help="Litres, crossings, units: what the amount bought.",
    )
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
    )
    raw_data = fields.Text(groups="wallet.group_wallet_manager")

    _external_ref_account_uniq = models.UniqueIndex(
        "(external_ref, account_id) NULLS NOT DISTINCT WHERE external_ref IS NOT NULL",
        "A transaction reference must be unique per wallet account.",
    )

    @api.depends("place", "date_transaction", "account_id.tz", "card_id.kind")
    def _compute_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for transaction in self:
            local = transaction._get_date_transaction_local()
            when = local.strftime("%Y-%m-%d %H:%M") if local else "?"
            what = transaction.place or kinds.get(transaction.kind, "Wallet")
            transaction.name = f"{what} - {when}"

    @api.depends("date_transaction", "account_id.tz")
    def _compute_date(self) -> None:
        for transaction in self:
            local = transaction._get_date_transaction_local()
            transaction.date = local.date() if local else False

    def _get_date_transaction_local(self):
        self.check_singleton()
        if not self.date_transaction:
            return None
        return self.date_transaction.replace(tzinfo=UTC).astimezone(
            ZoneInfo(self.account_id.tz or "UTC")
        )
