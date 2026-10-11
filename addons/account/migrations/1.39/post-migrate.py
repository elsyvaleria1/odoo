import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    drafts = env["account.move"].search(
        [
            ("state", "=", "draft"),
            ("invoice_date", "=", False),
            ("move_type", "in", ("out_invoice", "out_refund", "out_receipt")),
        ]
    )
    manual = drafts.filtered(
        lambda move: (
            move.currency_id != move.company_currency_id
            and float_compare(
                move.invoice_currency_rate,
                move._get_expected_currency_rate_at(move.create_date.date()),
                precision_digits=6,
            )
            != 0
        )
    )
    if not manual:
        return
    cr.execute(
        "UPDATE account_move SET is_invoice_currency_rate_manual = TRUE WHERE id = ANY(%s)",
        [manual.ids],
    )
    manual.invalidate_recordset(["is_invoice_currency_rate_manual"])
    _logger.info(
        "account: %s draft invoice(s) keep their hand-typed currency rate",
        len(manual),
    )
