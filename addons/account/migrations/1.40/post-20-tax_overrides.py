import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    AccountMove = env["account.move"]
    drafts = AccountMove.search(
        [
            ("state", "=", "draft"),
            ("move_type", "in", AccountMove.get_invoice_types(include_receipts=True)),
            ("line_ids.display_type", "=", "tax"),
        ]
    )
    drafts._capture_tax_overrides_from_tax_lines()
    captured = drafts.filtered("tax_override_ids")
    if captured:
        _logger.info(
            "account: %s draft invoice(s) carry hand-typed tax amounts, now recorded as manual tax amounts",
            len(captured),
        )
