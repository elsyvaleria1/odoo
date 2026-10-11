import csv
import io
import logging

from markupsafe import Markup

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_LIQUIDITY_DRIFT = """
    SELECT payment.id, payment.outstanding_account_id, line.account_id
      FROM account_payment payment
      JOIN account_move_line line
        ON line.move_id = payment.move_id AND line.payment_role = 'liquidity'
     WHERE payment.outstanding_account_id IS DISTINCT FROM line.account_id
     ORDER BY payment.id
"""

_COUNTERPART_DRIFT = """
    SELECT payment.id, payment.destination_account_id, line.account_id
      FROM account_payment payment
      JOIN account_move_line line
        ON line.move_id = payment.move_id AND line.payment_role = 'counterpart'
     WHERE payment.destination_account_id IS DISTINCT FROM line.account_id
     ORDER BY payment.id
"""

_F6_ALIGNED = """
    SELECT payment.id
      FROM account_payment payment
      JOIN account_move_line liquidity
        ON liquidity.move_id = payment.move_id AND liquidity.payment_role = 'liquidity'
      JOIN account_move_line counterpart
        ON counterpart.move_id = payment.move_id
       AND counterpart.payment_role = 'counterpart'
     WHERE payment.counterpart_review_required IS NOT TRUE
       AND (
            payment.outstanding_account_id IS DISTINCT FROM liquidity.account_id
            OR payment.destination_account_id IS DISTINCT FROM counterpart.account_id
       )
     ORDER BY payment.id
"""

_REPORT_HEADER = (
    "payment_id",
    "payment",
    "entry",
    "date",
    "partner",
    "partner_type",
    "payment_account",
    "entry_account",
    "entry_account_type",
    "reconciled",
    "customer_account_on_supplier_payment",
)


def _account_label(account, company):
    return account.with_company(company).display_name if account else ""


def _align_liquidity(env):
    cr = env.cr
    cr.execute(_LIQUIDITY_DRIFT)
    drift = cr.fetchall()
    if not drift:
        return
    cr.execute(
        """
        UPDATE account_payment payment
           SET outstanding_account_id = line.account_id
          FROM account_move_line line
         WHERE line.move_id = payment.move_id
           AND line.payment_role = 'liquidity'
           AND payment.outstanding_account_id IS DISTINCT FROM line.account_id
        """
    )
    env.invalidate_all()
    Account = env["account.account"]
    filled = 0
    for payment_id, old_id, new_id in drift:
        filled += not old_id
        env["account.payment"].browse(payment_id).message_post(
            body=Markup("%s")
            % env._(
                "Liquidity account aligned to the journal entry by account 1.42: "
                "%(old)s → %(new)s. The entry is what is posted and reconciled; "
                "nothing in it changed.",
                old=Account.browse(old_id).display_name or env._("none"),
                new=Account.browse(new_id).display_name,
            ),
            subtype_xmlid="mail.mt_note",
        )
    _logger.info(
        "account 1.42: liquidity account aligned to the entry on %s payments "
        "(%s were empty, %s differed)",
        len(drift),
        filled,
        len(drift) - filled,
    )


def _flag_counterpart_drift(env):
    cr = env.cr
    cr.execute(_COUNTERPART_DRIFT)
    drift = cr.fetchall()
    if not drift:
        return
    cr.execute(
        "UPDATE account_payment SET counterpart_review_required = TRUE WHERE id = ANY(%s)",
        [[payment_id for payment_id, _old, _new in drift]],
    )
    env.invalidate_all()
    Account = env["account.account"]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_REPORT_HEADER)
    mismatched_type = 0
    for payment_id, old_id, new_id in drift:
        payment = env["account.payment"].browse(payment_id)
        old, new = Account.browse(old_id), Account.browse(new_id)
        customer_on_supplier = (
            payment.partner_type == "supplier"
            and old.account_type == "asset_receivable"
        ) or (
            payment.partner_type == "customer"
            and old.account_type == "liability_payable"
        )
        mismatched_type += customer_on_supplier
        counterpart = payment.move_id.line_ids.filtered(
            lambda line: line.payment_role == "counterpart"
        )
        writer.writerow(
            (
                payment.id,
                payment.name,
                payment.move_id.name,
                payment.date,
                payment.partner_id.display_name or "",
                payment.partner_type,
                _account_label(old, payment.company_id),
                _account_label(new, payment.company_id),
                new.account_type,
                bool(counterpart.matched_debit_ids or counterpart.matched_credit_ids),
                customer_on_supplier,
            )
        )
    _logger.warning(
        "account 1.42: %s payments name a counterpart account their entry does not "
        "use (%s of them a customer account on a supplier payment, or the reverse). "
        "They are left unaligned and unlocked, flagged counterpart_review_required; "
        "after review apply Actions > Align Counterpart to Entry. Review list:\n%s",
        len(drift),
        mismatched_type,
        buffer.getvalue(),
    )


def _backfill_counterpart_source(env):
    env.cr.execute(
        """
        UPDATE account_payment payment
           SET counterpart_account_source = CASE
                   WHEN EXISTS (
                        SELECT 1 FROM account_partial_reconcile part
                         WHERE part.debit_move_id = line.id OR part.credit_move_id = line.id
                   ) THEN 'settled'
                   ELSE 'explicit'
               END
          FROM account_move_line line
         WHERE line.move_id = payment.move_id
           AND line.payment_role = 'counterpart'
           AND payment.counterpart_review_required IS NOT TRUE
        """
    )
    _logger.info(
        "account 1.42: counterpart account source recorded on %s payments",
        env.cr.rowcount,
    )


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    _align_liquidity(env)
    _flag_counterpart_drift(env)
    _backfill_counterpart_source(env)
    cr.execute(_F6_ALIGNED)
    if remaining := [payment_id for (payment_id,) in cr.fetchall()]:
        raise RuntimeError(
            "account 1.42: %s payments still disagree with their entry after the "
            "alignment, so the entry lock cannot be switched on: %s"
            % (len(remaining), ", ".join(map(str, remaining)))
        )
    _logger.info(
        "account 1.42: every payment not left for review agrees with its entry; "
        "the entry lock applies to them"
    )
