import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    AccountMove = env["account.move"]
    # before 1.40 a hand-typed tax amount lived only as tax lines drifting from
    # the computed amount; a posted entry keeps its lines as they are, and
    # action_draft records the drift of one that goes back to draft
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
