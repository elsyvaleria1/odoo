import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        SQL(
            """
            SELECT partial.id,
                   partial.amount,
                   debit.id,
                   debit.parent_state,
                   partial.debit_amount_currency,
                   credit.id,
                   credit.parent_state,
                   partial.credit_amount_currency
              FROM account_partial_reconcile partial
              JOIN account_move_line debit ON debit.id = partial.debit_move_id
              JOIN account_move_line credit ON credit.id = partial.credit_move_id
             WHERE debit.parent_state != 'posted' OR credit.parent_state != 'posted'
            """
        )
    )
    rows = cr.fetchall()
    if not rows:
        return
    Partial = env["account.partial.reconcile"]
    Line = env["account.move.line"]
    Move = env["account.move"]
    partials = Partial.browse([row[0] for row in rows])
    side_moves = (
        Move.search([("tax_cash_basis_rec_id", "in", partials.ids)])
        | partials.exchange_move_id
    ).filtered(lambda move: move.state == "draft")

    to_pend = []
    for (
        _partial_id,
        amount,
        debit_id,
        debit_state,
        debit_amount_currency,
        credit_id,
        credit_state,
        credit_amount_currency,
    ) in rows:
        if debit_state == "posted" and credit_state == "draft":
            posted, draft, amount_currency = (
                Line.browse(debit_id),
                Line.browse(credit_id),
                credit_amount_currency,
            )
        elif credit_state == "posted" and debit_state == "draft":
            posted, draft, amount_currency = (
                Line.browse(credit_id),
                Line.browse(debit_id),
                debit_amount_currency,
            )
        else:
            continue
        if draft.move_id in side_moves:
            continue
        to_pend.append((posted.id, draft.id, amount, amount_currency))

    side_moves.with_context(force_delete=True).unlink()
    partials.exists().unlink()

    vals_list = []
    for posted_id, draft_id, amount, amount_currency in to_pend:
        posted, draft = Line.browse(posted_id), Line.browse(draft_id)
        vals_list.append(
            {
                "posted_line_id": posted.id,
                "draft_line_id": draft.id,
                "amount": amount,
                "amount_currency": amount_currency,
                "currency_id": draft.currency_id.id,
                "origin": "bank_auto" if posted.move_id.statement_line_id else "manual",
            }
        )
    matches = env["account.pending.match"].create(vals_list)

    stale = Move.search(
        [("state", "!=", "posted"), ("payment_state", "!=", "not_paid")]
    )
    env.add_to_compute(Move._fields["payment_state"], stale)
    Move.flush_model(["payment_state"])
    _logger.info(
        "account: %s partials touching a draft removed with %s draft automatic "
        "entries; %s pending matches for %s kept the matches (%s draft moves "
        "reread their payment state)",
        len(partials),
        len(side_moves),
        len(matches),
        sum(matches.mapped("amount")),
        len(stale),
    )
