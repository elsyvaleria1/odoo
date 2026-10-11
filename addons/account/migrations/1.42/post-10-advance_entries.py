import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    Payment = env["account.payment"]
    cr.execute(
        SQL(
            """
            SELECT payment.id
              FROM account_payment payment
             WHERE payment.move_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM account_move_line line
                      JOIN account_account account ON account.id = line.account_id
                     WHERE line.move_id = payment.move_id
                       AND account.account_type = ANY(%s)
               )
             ORDER BY payment.id
            """,
            list(Payment._get_liquidity_account_types()),
        )
    )
    payments = Payment.browse([payment_id for (payment_id,) in cr.fetchall()])
    if not payments:
        return
    _logger.info(
        "account 1.42: %s payments move no money and become journal entries: %s",
        len(payments),
        ", ".join(f"{pay.id} ({pay.move_id.name})" for pay in payments),
    )
    payments._convert_to_entry()
