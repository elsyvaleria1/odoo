import logging
from collections import defaultdict
from itertools import batched

from odoo import SUPERUSER_ID, Command, api
from odoo.tools import SQL, float_is_zero

from odoo.addons.account.models.account_account import RECONCILABLE_WITHOUT_FLAG_TYPES

_logger = logging.getLogger(__name__)

RESIDUAL_FIELDS = ("amount_residual", "amount_residual_currency", "reconciled")
BATCH_SIZE = 5000
SAMPLE_SIZE = 5000


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _normalise_reconcilable(env)
    changed_ids = _recompute_residuals(env)
    _check_against_compute(env, changed_ids)
    _recompute_residual_dependents(env, changed_ids)
    _remove_over_reconciling_partials(env)
    _rebuild_split_full_reconciles(env)


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


def _normalise_reconcilable(env) -> None:
    cr = env.cr
    env.flush_all()
    cr.execute(
        SQL(
            """
            UPDATE account_account
               SET is_reconcilable = COALESCE(reconcile OR account_type = ANY(%(types)s), FALSE)
             WHERE is_reconcilable IS DISTINCT FROM (
                    COALESCE(reconcile OR account_type = ANY(%(types)s), FALSE)
                   )
         RETURNING id, is_reconcilable
            """,
            types=list(RECONCILABLE_WITHOUT_FLAG_TYPES),
        )
    )
    rows = [
        ("F1/F2", "is_reconcilable", "fixed", "account.account", account_id)
        + (None, None, None, f"is_reconcilable set to {value}")
        for account_id, value in cr.fetchall()
    ]
    env["account.account"].invalidate_model(["is_reconcilable"])
    _report(cr, rows)
    if rows:
        _logger.info("account: %s account(s) state whether they reconcile", len(rows))


def _recompute_residuals(env) -> list[int]:
    cr = env.cr
    env.flush_all()
    cr.execute(
        SQL(
            """
            CREATE TEMP TABLE account_141_residual AS
            SELECT *
              FROM (
                    SELECT line.id,
                           line.company_id,
                           line.account_id,
                           line.date,
                           line.amount_residual AS old_residual,
                           line.amount_residual_currency AS old_residual_currency,
                           line.reconciled AS old_reconciled,
                           CASE WHEN needs.residual THEN computed.residual ELSE 0 END::float8 AS residual,
                           CASE WHEN needs.residual THEN computed.residual_currency ELSE 0 END::float8
                               AS residual_currency,
                           needs.residual AND computed.residual = 0 AND computed.residual_currency = 0
                               AS reconciled
                      FROM account_move_line line
                      JOIN res_company company ON company.id = line.company_id
                      JOIN res_currency company_currency ON company_currency.id = company.currency_id
                      JOIN res_currency currency ON currency.id = COALESCE(line.currency_id, company.currency_id)
                 LEFT JOIN account_account account ON account.id = line.account_id
                 LEFT JOIN (
                            SELECT debit_move_id AS line_id,
                                   SUM(amount) AS amount,
                                   SUM(debit_amount_currency) AS amount_currency
                              FROM account_partial_reconcile
                          GROUP BY debit_move_id
                           ) debit ON debit.line_id = line.id
                 LEFT JOIN (
                            SELECT credit_move_id AS line_id,
                                   SUM(amount) AS amount,
                                   SUM(credit_amount_currency) AS amount_currency
                              FROM account_partial_reconcile
                          GROUP BY credit_move_id
                           ) credit ON credit.line_id = line.id
                     CROSS JOIN LATERAL (
                            SELECT COALESCE(account.is_reconcilable, FALSE) AS residual
                           ) needs
                     CROSS JOIN LATERAL (
                            SELECT ROUND(
                                       (line.balance - COALESCE(debit.amount, 0) + COALESCE(credit.amount, 0))
                                       / company_currency.rounding
                                   ) * company_currency.rounding AS residual,
                                   ROUND(
                                       (line.amount_currency
                                        - ROUND(COALESCE(debit.amount_currency, 0) / currency.rounding)
                                          * currency.rounding
                                        + ROUND(COALESCE(credit.amount_currency, 0) / currency.rounding)
                                          * currency.rounding)
                                       / currency.rounding
                                   ) * currency.rounding AS residual_currency
                           ) computed
                   ) fix
             WHERE old_residual IS DISTINCT FROM residual
                OR old_residual_currency IS DISTINCT FROM residual_currency
                OR old_reconciled IS DISTINCT FROM reconciled
            """
        )
    )
    cr.execute(
        """
        UPDATE account_move_line line
           SET amount_residual = fix.residual,
               amount_residual_currency = fix.residual_currency,
               reconciled = fix.reconciled
          FROM account_141_residual fix
         WHERE line.id = fix.id
        """
    )
    env["account.move.line"].invalidate_model(list(RESIDUAL_FIELDS))
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F1/F2', 'residual', 'fixed', 'account.move.line', fix.id, fix.company_id,
               to_char(fix.date, 'YYYY'), fix.residual - COALESCE(fix.old_residual, 0),
               CONCAT('account ', COALESCE(account.code_store->>fix.company_id::text, fix.account_id::text),
                      ': residual ', fix.old_residual, ' -> ', fix.residual,
                      ', currency residual ', fix.old_residual_currency, ' -> ', fix.residual_currency,
                      ', reconciled ', fix.old_reconciled, ' -> ', fix.reconciled)
          FROM account_141_residual fix
     LEFT JOIN account_account account ON account.id = fix.account_id
        """
    )
    cr.execute(
        """
        SELECT fix.account_id, COUNT(*)
          FROM account_141_residual fix
      GROUP BY fix.account_id
      ORDER BY COUNT(*) DESC, fix.account_id
        """
    )
    per_account = cr.fetchall()
    cr.execute("SELECT id FROM account_141_residual ORDER BY id")
    changed_ids = [line_id for (line_id,) in cr.fetchall()]
    cr.execute("DROP TABLE account_141_residual")
    if changed_ids:
        _logger.info(
            "account: %s journal item(s) now carry the residual their partials give (per account id: %s)",
            len(changed_ids),
            ", ".join(f"{account_id}: {count}" for account_id, count in per_account),
        )
    return changed_ids


def _read_residuals(cr, line_ids) -> dict:
    cr.execute(
        SQL(
            """
            SELECT id, amount_residual, amount_residual_currency, reconciled
              FROM account_move_line
             WHERE id = ANY(%s)
            """,
            list(line_ids),
        )
    )
    return {
        line_id: (float(residual or 0), float(residual_currency or 0), bool(reconciled))
        for line_id, residual, residual_currency, reconciled in cr.fetchall()
    }


def _check_against_compute(env, changed_ids) -> None:
    cr = env.cr
    cr.execute(
        SQL(
            """
            SELECT id
              FROM (
                    SELECT debit_move_id AS id FROM account_partial_reconcile
                     UNION
                    SELECT credit_move_id FROM account_partial_reconcile
                   ) reconciled_line
          ORDER BY random()
             LIMIT %s
            """,
            SAMPLE_SIZE,
        )
    )
    sample = sorted({line_id for (line_id,) in cr.fetchall()} | set(changed_ids))
    Line = env["account.move.line"]
    fields = [Line._fields[fname] for fname in RESIDUAL_FIELDS]
    mismatches = []
    for ids in batched(sample, BATCH_SIZE, strict=False):
        stored = _read_residuals(cr, ids)
        lines = Line.browse(ids)
        for field in fields:
            env.add_to_compute(field, lines)
        for line in lines:
            computed = (
                line.amount_residual,
                line.amount_residual_currency,
                line.reconciled,
            )
            expected = stored[line.id]
            if computed[2] != expected[2] or any(
                not float_is_zero(a - b, precision_digits=6)
                for a, b in zip(computed[:2], expected[:2], strict=True)
            ):
                mismatches.append((line.id, expected, computed))
        env.flush_all()
        env.invalidate_all()
    if mismatches:
        raise RuntimeError(
            "account 1.41: the set-based residuals differ from the compute on "
            f"{len(mismatches)} journal item(s), first: {mismatches[:10]}"
        )
    _logger.info(
        "account: the residuals of %s journal item(s) match _compute_reconciliation",
        len(sample),
    )


DEPENDENT_SNAPSHOTS = (
    (
        "account.move",
        "account_move",
        ("amount_residual", "amount_residual_signed", "payment_state"),
    ),
    (
        "account.payment",
        "account_payment",
        ("state", "is_bank_matched", "is_invoice_reconciled"),
    ),
    (
        "account.bank.statement.line",
        "account_bank_statement_line",
        ("is_reconciled", "amount_residual"),
    ),
)
FINDING_BY_DEPENDENT = {
    ("account.move", "payment_state"): ("F8", "payment_state"),
    ("account.payment", "state"): ("F11", "payment_state"),
}


def _snapshot(cr, table, columns) -> dict:
    cr.execute(
        SQL(
            "SELECT id, %s FROM %s",
            SQL(", ").join(SQL.identifier(column) for column in columns),
            SQL.identifier(table),
        )
    )
    return {row[0]: row[1:] for row in cr.fetchall()}


def _recompute_residual_dependents(env, changed_ids) -> None:
    if not changed_ids:
        return
    cr = env.cr
    before = {
        model: (columns, _snapshot(cr, table, columns))
        for model, table, columns in DEPENDENT_SNAPSHOTS
    }
    env["account.move.line"].browse(changed_ids).modified(list(RESIDUAL_FIELDS))
    env.flush_all()
    rows = []
    for model, table, columns in DEPENDENT_SNAPSHOTS:
        old_values = before[model][1]
        new_values = _snapshot(cr, table, columns)
        changed = 0
        for record_id, values in old_values.items():
            if new_values.get(record_id) == values:
                continue
            changed += 1
            for column, old, new in zip(
                columns, values, new_values[record_id], strict=True
            ):
                if old != new:
                    finding, kind = FINDING_BY_DEPENDENT.get(
                        (model, column), ("F1/F2", "residual_dependent")
                    )
                    rows.append(
                        (finding, kind, "fixed", model, record_id)
                        + (None, None, None, f"{column} {old} -> {new}")
                    )
        if changed:
            _logger.info(
                "account: %s %s record(s) follow the repaired residuals",
                changed,
                model,
            )
    _report(cr, rows)
    env.invalidate_all()


def _over_reconciled_lines(cr) -> list[tuple]:
    cr.execute(
        """
        SELECT line.id, line.balance, line.amount_residual, line.amount_currency,
               line.amount_residual_currency, company_currency.rounding, currency.rounding
          FROM account_move_line line
          JOIN res_company company ON company.id = line.company_id
          JOIN res_currency company_currency ON company_currency.id = company.currency_id
          JOIN res_currency currency ON currency.id = COALESCE(line.currency_id, company.currency_id)
         WHERE SIGN(line.amount_residual) * SIGN(line.balance) < 0
            OR SIGN(line.amount_residual_currency) * SIGN(line.amount_currency) < 0
      ORDER BY line.id
        """
    )
    return cr.fetchall()


def _is_flipped(total, residual, rounding) -> bool:
    return total * residual < 0 and not float_is_zero(
        residual, precision_rounding=rounding
    )


def _remove_over_reconciling_partials(env) -> None:
    cr = env.cr
    over_lines = _over_reconciled_lines(cr)
    if not over_lines:
        return
    cr.execute(
        SQL(
            """
            SELECT id, debit_move_id, credit_move_id, amount,
                   debit_amount_currency, credit_amount_currency
              FROM account_partial_reconcile
             WHERE debit_move_id = ANY(%(ids)s) OR credit_move_id = ANY(%(ids)s)
          ORDER BY create_date DESC, id DESC
            """,
            ids=[line[0] for line in over_lines],
        )
    )
    partials_by_line = defaultdict(list)
    for partial in cr.fetchall():
        partials_by_line[partial[1]].append(partial)
        partials_by_line[partial[2]].append(partial)
    to_remove = set()
    unresolved = []
    for (
        line_id,
        balance,
        residual,
        amount_currency,
        residual_currency,
        company_rounding,
        rounding,
    ) in over_lines:
        residual, residual_currency = float(residual), float(residual_currency)
        balance, amount_currency = float(balance), float(amount_currency)

        def release(partial, line_id=line_id) -> tuple[float, float]:
            _id, debit_id, _credit_id, amount, debit_currency, credit_currency = partial
            if debit_id == line_id:
                return float(amount), float(debit_currency)
            return -float(amount), -float(credit_currency)

        partials = partials_by_line[line_id]
        for partial in partials:
            if partial[0] in to_remove:
                amount, amount_in_currency = release(partial)
                residual += amount
                residual_currency += amount_in_currency
        for partial in partials:
            if not (
                _is_flipped(balance, residual, float(company_rounding))
                or _is_flipped(amount_currency, residual_currency, float(rounding))
            ):
                break
            if partial[0] in to_remove:
                continue
            amount, amount_in_currency = release(partial)
            residual += amount
            residual_currency += amount_in_currency
            to_remove.add(partial[0])
        else:
            if _is_flipped(balance, residual, float(company_rounding)):
                unresolved.append(line_id)
    Partial = env["account.partial.reconcile"]
    partials = Partial.browse(sorted(to_remove))
    lines = partials.debit_move_id | partials.credit_move_id
    caba_moves = env["account.move"].search(
        [("tax_cash_basis_rec_id", "in", partials.ids)]
    )
    rows = [
        (
            "F1",
            "over_reconciling_partial",
            "fixed",
            "account.partial.reconcile",
            partial.id,
            partial.company_id.id,
            str(partial.max_date or ""),
            partial.amount,
            f"removed: matched {partial.debit_move_id.display_name} (line "
            f"{partial.debit_move_id.id}) with {partial.credit_move_id.display_name} "
            f"(line {partial.credit_move_id.id}), created {partial.create_date} by "
            f"{partial.create_uid.login}"
            + (
                f", exchange entry {partial.exchange_move_id.name}"
                if partial.exchange_move_id
                else ""
            ),
        )
        for partial in partials
    ]
    rows.extend(
        (
            "F1",
            "over_reconciled_line",
            "accountant",
            "account.move.line",
            line_id,
            None,
            None,
            None,
            "still matched for more than its amount after removing its newest partials",
        )
        for line_id in unresolved
    )
    partials.unlink()
    env.flush_all()
    lines = lines.exists()
    lines.invalidate_recordset(list(RESIDUAL_FIELDS))
    rows.extend(
        (
            "F1",
            "line_to_rematch",
            "accountant",
            "account.move.line",
            line.id,
            line.company_id.id,
            str(line.date),
            line.amount_residual,
            (
                f"{line.move_id.name} on {line.account_id.code}: open for "
                f"{line.amount_residual} after the over-reconciling partials were removed"
            ),
        )
        for line in lines
        if not line.reconciled
    )
    _report(cr, rows)
    _logger.info(
        "account: removed %s over-reconciling partial(s) %s (cash-basis entries %s); "
        "%s line(s) to match again: %s",
        len(partials),
        partials.ids,
        caba_moves.ids,
        len(lines.filtered(lambda line: not line.reconciled)),
        lines.filtered(lambda line: not line.reconciled).ids,
    )
    if unresolved:
        _logger.warning(
            "account: %s line(s) stay over-reconciled and need the accountant: %s",
            len(unresolved),
            unresolved,
        )


def _component(cr, line_ids) -> tuple[set, set]:
    lines, partials, frontier = set(line_ids), set(), set(line_ids)
    while frontier:
        cr.execute(
            SQL(
                """
                SELECT id, debit_move_id, credit_move_id
                  FROM account_partial_reconcile
                 WHERE debit_move_id = ANY(%(ids)s) OR credit_move_id = ANY(%(ids)s)
                 UNION ALL
                SELECT NULL, line.id, line.id
                  FROM account_move_line line
                 WHERE line.full_reconcile_id IN (
                        SELECT full_reconcile_id
                          FROM account_move_line
                         WHERE id = ANY(%(ids)s) AND full_reconcile_id IS NOT NULL
                       )
                """,
                ids=list(frontier),
            )
        )
        reached = set()
        for partial_id, debit_id, credit_id in cr.fetchall():
            if partial_id:
                partials.add(partial_id)
            reached.update((debit_id, credit_id))
        frontier = reached - lines
        lines |= reached
    return lines, partials


def _rebuild_split_full_reconciles(env) -> None:
    cr = env.cr
    cr.execute(
        """
        SELECT debit.id
          FROM account_partial_reconcile partial
          JOIN account_move_line debit ON debit.id = partial.debit_move_id
          JOIN account_move_line credit ON credit.id = partial.credit_move_id
         WHERE partial.full_reconcile_id IS DISTINCT FROM debit.full_reconcile_id
            OR partial.full_reconcile_id IS DISTINCT FROM credit.full_reconcile_id
         UNION
        SELECT id
          FROM account_move_line
         WHERE full_reconcile_id IS NOT NULL AND NOT reconciled
        """
    )
    seeds = [line_id for (line_id,) in cr.fetchall()]
    Line = env["account.move.line"]
    FullReconcile = env["account.full.reconcile"]
    done, rows = set(), []
    for seed in seeds:
        if seed in done:
            continue
        line_ids, partial_ids = _component(cr, [seed])
        done |= line_ids
        lines = Line.browse(sorted(line_ids))
        old_fulls = lines.full_reconcile_id
        company_currency = lines.company_currency_id[:1]
        if not all(lines.mapped("reconciled")) or not company_currency.is_zero(
            sum(lines.mapped("balance"))
        ):
            rows.append(
                (
                    "F13",
                    "full_reconcile_split",
                    "accountant",
                    "account.full.reconcile",
                    old_fulls[:1].id,
                    lines.company_id[:1].id,
                    None,
                    sum(lines.mapped("amount_residual")),
                    (
                        f"lines {lines.ids} are not all reconciled: the full "
                        "reconcile cannot be rebuilt"
                    ),
                )
            )
            continue
        old_ids = old_fulls.ids
        old_fulls.with_context(defer_matching_number_update=True).unlink()
        full = FullReconcile.create(
            {
                "partial_reconcile_ids": [
                    Command.link(partial_id) for partial_id in sorted(partial_ids)
                ],
                "reconciled_line_ids": [Command.link(line_id) for line_id in lines.ids],
            }
        )
        rows.append(
            (
                "F13",
                "full_reconcile_split",
                "fixed",
                "account.full.reconcile",
                full.id,
                full.company_id.id,
                None,
                None,
                (
                    f"full reconcile(s) {old_ids} rebuilt as {full.id} over lines "
                    f"{lines.ids} and partials {sorted(partial_ids)}"
                ),
            )
        )
        _logger.info(
            "account: full reconcile(s) %s rebuilt as %s over %s line(s) and %s partial(s)",
            old_ids,
            full.id,
            len(lines),
            len(partial_ids),
        )
    env.flush_all()
    _report(cr, rows)
