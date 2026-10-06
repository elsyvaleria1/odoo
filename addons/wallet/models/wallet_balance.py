import logging
from datetime import timedelta
from itertools import batched

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
UNLINK_BATCH_SIZE = 500
SUPERSEDED_SNAPSHOTS_SQL = """
    SELECT id FROM (
        SELECT id, row_number() OVER (
                   PARTITION BY card_id, date::date
                   ORDER BY date DESC, id DESC) AS rank
          FROM wallet_balance
         WHERE date < %s) ranked
     WHERE rank > 1
"""
LATEST_BY_CARD_SQL = """
    SELECT DISTINCT ON (card_id) card_id, id
      FROM wallet_balance
     WHERE card_id = ANY(%s)
  ORDER BY card_id, date DESC, id DESC
"""


class WalletBalance(models.Model):
    _name = "wallet.balance"
    _description = "Electronic Wallet Balance Snapshot"
    _order = "date desc, card_id, id desc"

    # FIELDS
    card_id = fields.Many2one(
        comodel_name="wallet.card",
        index=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        related="card_id.account_id",
    )
    company_id = fields.Many2one(
        related="card_id.company_id",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    amount_balance = fields.Monetary(required=True)
    source = fields.Selection(
        selection=[
            ("manual", "Manual Entry"),
            ("import", "Imported"),
        ],
        default="manual",
        required=True,
    )
    status = fields.Char(
        help="What the issuer reported about the card at that instant."
    )

    # CONSTRAINTS
    _card_date_uniq = models.Constraint(
        "UNIQUE(card_id, date)",
        "A card holds one balance snapshot per instant.",
    )

    # HELPER METHODS
    @api.model
    def _get_latest_by_card(self, cards) -> dict:
        """{card id: latest snapshot} for the cards that have one."""
        if not cards.ids:
            return {}
        self.flush_model(["card_id", "date", "amount_balance"])
        self.env.cr.execute(LATEST_BY_CARD_SQL, [list(cards.ids)])
        rows = self.env.cr.fetchall()
        snapshots = self.browse([row[1] for row in rows])
        by_id = {snapshot.id: snapshot for snapshot in snapshots}
        return {card_id: by_id[snapshot_id] for card_id, snapshot_id in rows}

    @api.model
    def _cron_downsample_old_balances(self, retention_days=RETENTION_DAYS) -> int:
        cutoff = fields.Datetime.now() - timedelta(days=retention_days)
        self.env.cr.execute(SUPERSEDED_SNAPSHOTS_SQL, [cutoff])
        superseded = [row[0] for row in self.env.cr.fetchall()]
        commit_progress = self.env["ir.cron"]._commit_progress
        commit_progress(0, remaining=len(superseded))
        for batch_ids in batched(superseded, UNLINK_BATCH_SIZE, strict=False):
            self.browse(batch_ids).unlink()
            if not commit_progress(processed=len(batch_ids)):
                break
        if superseded:
            _logger.info(
                "Downsampled %d wallet balance snapshots older than %d days to "
                "one a day.",
                len(superseded),
                retention_days,
            )
        return len(superseded)
