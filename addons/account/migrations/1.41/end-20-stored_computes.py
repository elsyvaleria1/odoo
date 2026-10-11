import logging
from itertools import batched

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

BATCH_SIZE = 5000
MAX_ROUNDS = 4
MOVE_AMOUNT_FIELDS = (
    "amount_untaxed",
    "amount_tax",
    "amount_total",
    "amount_residual",
    "amount_untaxed_signed",
    "amount_untaxed_in_currency_signed",
    "amount_tax_signed",
    "amount_total_signed",
    "amount_total_in_currency_signed",
    "amount_residual_signed",
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _recompute_commercial_partners(env)
    _recompute_payment_states(env)
    _recompute_sequence_split(env)
    _recompute_statement_balances(env)
    _recompute_untaxed_in_currency(env)
    _recompute_partial_max_dates(env)
    _repair_price_rounding(env)


class _Discard(Exception):
    pass


def _report(cr, rows):
    if rows:
        cr.execute_values(
            """
            INSERT INTO account_repair_141_report
                   (finding, kind, action, model, res_id, company_id, period, amount, detail)
            VALUES %s
            """,
            rows,
            page_size=1000,
        )


def _ids(cr, query) -> list[int]:
    cr.execute(query)
    return [record_id for (record_id,) in cr.fetchall()]


def _read_columns(cr, table, columns, ids) -> dict:
    cr.execute(
        SQL(
            "SELECT id, %s FROM %s WHERE id = ANY(%s)",
            SQL(", ").join(SQL.identifier(column) for column in columns),
            SQL.identifier(table),
            list(ids),
        )
    )
    return {row[0]: row[1:] for row in cr.fetchall()}


def _recompute_stored(env, model, fnames, ids, finding, kind) -> list[int]:
    Model = env[model]
    changed, rows = [], []
    for batch in batched(sorted(ids), BATCH_SIZE, strict=False):
        before = _read_columns(env.cr, Model._table, fnames, batch)
        records = Model.browse(batch)
        for fname in fnames:
            env.add_to_compute(Model._fields[fname], records)
        env.flush_all()
        after = _read_columns(env.cr, Model._table, fnames, batch)
        for record_id in batch:
            if before[record_id] == after[record_id]:
                continue
            changed.append(record_id)
            rows.append(
                (
                    finding,
                    kind,
                    "fixed",
                    model,
                    record_id,
                    None,
                    None,
                    None,
                    ", ".join(
                        f"{fname} {old} -> {new}"
                        for fname, old, new in zip(
                            fnames, before[record_id], after[record_id], strict=True
                        )
                        if old != new
                    ),
                )
            )
        env.invalidate_all()
    _report(env.cr, rows)
    return changed


def _recompute_commercial_partners(env) -> None:
    ids = _ids(
        env.cr,
        """
        SELECT move.id
          FROM account_move move
     LEFT JOIN res_partner partner ON partner.id = move.partner_id
         WHERE move.commercial_partner_id IS DISTINCT FROM partner.commercial_partner_id
        """,
    )
    changed = _recompute_stored(
        env, "account.move", ("commercial_partner_id",), ids, "F7", "commercial_partner"
    )
    if changed:
        _logger.info(
            "account: %s journal entr(ies) take their partner's commercial entity",
            len(changed),
        )


def _recompute_payment_states(env) -> None:
    cr = env.cr
    Move = env["account.move"]
    move_ids = _ids(
        cr,
        SQL(
            """
            SELECT id
              FROM account_move
             WHERE move_type = ANY(%s)
                OR payment_state IS NULL
                OR payment_state != 'not_paid'
            """,
            Move.get_invoice_types(include_receipts=True),
        ),
    )
    payment_ids = _ids(cr, "SELECT id FROM account_payment")
    changed_moves = _recompute_stored(
        env, "account.move", ("payment_state",), move_ids, "F8", "payment_state"
    )
    changed_payments = _recompute_stored(
        env, "account.payment", ("state",), payment_ids, "F11", "payment_state"
    )
    total_moves, total_payments = set(changed_moves), set(changed_payments)
    rounds = 0
    while (changed_moves or changed_payments) and rounds < MAX_ROUNDS:
        rounds += 1
        moves_before = _read_columns(cr, "account_move", ("payment_state",), move_ids)
        payments_before = _read_columns(cr, "account_payment", ("state",), payment_ids)
        Move.browse(changed_moves).modified(["payment_state"])
        env["account.payment"].browse(changed_payments).modified(["state"])
        env.flush_all()
        env.invalidate_all()
        moves_after = _read_columns(cr, "account_move", ("payment_state",), move_ids)
        payments_after = _read_columns(cr, "account_payment", ("state",), payment_ids)
        changed_moves = [
            move_id
            for move_id, values in moves_after.items()
            if moves_before[move_id] != values
        ]
        changed_payments = [
            payment_id
            for payment_id, values in payments_after.items()
            if payments_before[payment_id] != values
        ]
        _report(
            cr,
            [
                (
                    "F8",
                    "payment_state",
                    "fixed",
                    "account.move",
                    move_id,
                    None,
                    None,
                    None,
                    f"payment_state {moves_before[move_id][0]} -> {moves_after[move_id][0]}",
                )
                for move_id in changed_moves
            ]
            + [
                (
                    "F11",
                    "payment_state",
                    "fixed",
                    "account.payment",
                    payment_id,
                    None,
                    None,
                    None,
                    f"state {payments_before[payment_id][0]} -> {payments_after[payment_id][0]}",
                )
                for payment_id in changed_payments
            ],
        )
        total_moves.update(changed_moves)
        total_payments.update(changed_payments)
    if changed_moves or changed_payments:
        _logger.warning(
            "account: payment states still moving after %s rounds: entries %s, payments %s",
            MAX_ROUNDS,
            changed_moves[:50],
            changed_payments[:50],
        )
    if total_moves or total_payments:
        _logger.info(
            "account: %s journal entr(ies) and %s payment(s) take their computed payment state",
            len(total_moves),
            len(total_payments),
        )


def _recompute_sequence_split(env) -> None:
    ids = _ids(
        env.cr,
        """
        SELECT id
          FROM account_move
         WHERE name IS NOT NULL AND name != '/'
           AND (sequence_prefix IS NULL OR sequence_number IS NULL)
        """,
    )
    changed = _recompute_stored(
        env,
        "account.move",
        ("sequence_prefix", "sequence_number"),
        ids,
        "F5",
        "sequence_split",
    )
    if changed:
        _logger.info(
            "account: %s journal entr(ies) get the prefix and number of their name",
            len(changed),
        )


def _recompute_statement_balances(env) -> None:
    ids = _ids(env.cr, "SELECT id FROM account_bank_statement")
    changed = _recompute_stored(
        env,
        "account.bank.statement",
        ("balance_end", "first_line_index"),
        ids,
        "F12",
        "statement",
    )
    if changed:
        _logger.info(
            "account: %s bank statement(s) recompute their balance or first line: %s",
            len(changed),
            changed,
        )


def _recompute_untaxed_in_currency(env) -> None:
    ids = _ids(
        env.cr,
        """
        SELECT id
          FROM account_move
         WHERE amount_untaxed_in_currency_signed IS NULL
            OR (amount_untaxed_in_currency_signed = 0 AND amount_untaxed != 0)
        """,
    )
    changed = _recompute_stored(
        env, "account.move", MOVE_AMOUNT_FIELDS, ids, "F15", "move_amounts"
    )
    if changed:
        _logger.info(
            "account: %s journal entr(ies) recompute their untaxed amount in currency",
            len(changed),
        )


def _recompute_partial_max_dates(env) -> None:
    ids = _ids(
        env.cr,
        """
        SELECT partial.id
          FROM account_partial_reconcile partial
          JOIN account_move_line debit ON debit.id = partial.debit_move_id
          JOIN account_move_line credit ON credit.id = partial.credit_move_id
         WHERE partial.max_date IS DISTINCT FROM GREATEST(debit.date, credit.date)
        """,
    )
    changed = _recompute_stored(
        env,
        "account.partial.reconcile",
        ("max_date",),
        ids,
        "F15",
        "partial_max_date",
    )
    if changed:
        _logger.info(
            "account: %s partial reconcile(s) recompute their max date: %s",
            len(changed),
            changed,
        )


def _repair_price_rounding(env) -> None:
    cr = env.cr
    Line = env["account.move.line"]
    ids = _ids(
        cr,
        """
        SELECT line.id
          FROM account_move_line line
          JOIN account_move move ON move.id = line.move_id
         WHERE move.move_type != 'entry' AND line.display_type = 'product'
        """,
    )
    fields = ("price_subtotal", "price_total")
    fixes, rows = [], []
    for batch in batched(ids, BATCH_SIZE, strict=False):
        before = _read_columns(cr, "account_move_line", fields, batch)
        records = Line.browse(batch)
        try:
            with cr.savepoint():
                for fname in fields:
                    env.add_to_compute(Line._fields[fname], records)
                env.flush_all()
                after = _read_columns(cr, "account_move_line", fields, batch)
                raise _Discard
        except _Discard:
            pass
        env.invalidate_all()
        for line_id in batch:
            gaps = [
                abs(float(new or 0) - float(old or 0))
                for old, new in zip(before[line_id], after[line_id], strict=True)
            ]
            if not any(gap >= 0.005 for gap in gaps):
                continue
            detail = ", ".join(
                f"{fname} {old} -> {new}"
                for fname, old, new in zip(
                    fields, before[line_id], after[line_id], strict=True
                )
                if old != new
            )
            if all(gap < 0.015 for gap in gaps):
                fixes.append((line_id, *after[line_id]))
                rows.append(
                    ("F15", "price_rounding", "fixed", "account.move.line", line_id)
                    + (None, None, None, detail)
                )
            else:
                rows.append(
                    ("F15", "price_drift", "report", "account.move.line", line_id)
                    + (None, None, None, detail)
                )
    if fixes:
        cr.execute_values(
            """
            UPDATE account_move_line line
               SET price_subtotal = fix.price_subtotal::numeric,
                   price_total = fix.price_total::numeric
              FROM (VALUES %s) AS fix(id, price_subtotal, price_total)
             WHERE line.id = fix.id
            """,
            fixes,
            page_size=1000,
        )
        Line.invalidate_model(list(fields))
    _report(cr, rows)
    _logger.info(
        "account: %s invoice line(s) take their computed subtotal or total back from a "
        "cent of rounding; %s drift further and are listed",
        len(fixes),
        len(rows) - len(fixes),
    )
