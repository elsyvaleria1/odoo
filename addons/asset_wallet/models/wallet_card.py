from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

LOG_TYPE_BY_KIND = {"fuel": "fuel", "toll": "highway"}


class WalletCard(models.Model):
    _inherit = "wallet.card"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        ondelete="set null",
        check_company=True,
        help="The asset that carries the card.",
    )
    trace_id = fields.Many2one(
        related="asset_id.trace_id",
        store=True,
    )
    license_plate = fields.Char(related="asset_id.license_plate")
    opening_balance = fields.Monetary(
        help="The balance the card started with. Until the issuer reports a "
        "balance, the balance is this less what the asset's ledger books on "
        "the card."
    )
    amount_budget = fields.Monetary(
        related="reorder_rule_id.amount_max",
        string="Budget",
        readonly=False,
        help="The balance the card is reloaded up to: its reordering rule's maximum.",
    )

    def _get_ledger_spend(self):
        carded = self.filtered("asset_id")
        if not carded:
            return {}
        spend = {}
        rows = (
            self.env["resource.log"]
            .sudo()
            ._read_group(
                [
                    ("asset_id", "in", carded.asset_id.ids),
                    ("log_type", "in", list(LOG_TYPE_BY_KIND.values())),
                    ("state", "=", "done"),
                ],
                ["asset_id", "log_type"],
                ["amount:sum"],
            )
        )
        by_asset_type = {(asset.id, log_type): total for asset, log_type, total in rows}
        _debug.perf.count("ledger_spend_read", cards=carded, groups=len(rows))
        for card in carded:
            log_type = LOG_TYPE_BY_KIND.get(card.kind)
            spend[card.id] = by_asset_type.get((card.asset_id.id, log_type), 0.0)
        return spend

    @api.depends(
        "opening_balance",
        "asset_id.log_ids.state",
        "asset_id.log_ids.amount",
        "asset_id.log_ids.log_type",
        "asset_id.log_ids.active",
    )
    def _compute_amount_balance(self) -> None:
        super()._compute_amount_balance()
        unreported = self.filtered(lambda card: not card.date_balance)
        _debug.logic("balance_from_ledger", cards=self, unreported=len(unreported))
        spend = unreported._get_ledger_spend()
        for card in unreported:
            card.amount_balance = card.opening_balance - spend.get(card.id, 0.0)
