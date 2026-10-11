import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)

_CLASSIFY_PAYMENT_LINES = SQL("""
    CREATE TEMP TABLE payarch_payment_line_role ON COMMIT DROP AS
    WITH pay AS (
        SELECT p.id, p.move_id, p.journal_id, p.payment_channel_id, p.liquidity_account_id
          FROM account_payment p
         WHERE p.move_id IS NOT NULL
    ),
    liquidity_account AS (
        SELECT pay.id AS payment_id, x.account_id
          FROM pay
          JOIN account_journal j ON j.id = pay.journal_id
         CROSS JOIN LATERAL (
                SELECT j.default_account_id
                 UNION SELECT ch.payment_account_id
                         FROM account_payment_channel ch
                        WHERE ch.id = pay.payment_channel_id
                 UNION SELECT ch.payment_account_id
                         FROM account_payment_channel ch
                        WHERE ch.journal_id = pay.journal_id
                 UNION SELECT pay.liquidity_account_id
               ) x(account_id)
         WHERE x.account_id IS NOT NULL
    ),
    guess AS (
        SELECT pay.id AS payment_id,
               line.id AS line_id,
               CASE
                   WHEN EXISTS (
                        SELECT 1 FROM liquidity_account la
                         WHERE la.payment_id = pay.id AND la.account_id = line.account_id
                   ) THEN 'liquidity'
                   WHEN account.account_type IN ('asset_receivable', 'liability_payable')
                     OR line.account_id = config.transfer_account_id THEN 'counterpart'
                   ELSE 'other'
               END AS guess
          FROM pay
          JOIN account_move_line line ON line.move_id = pay.move_id
          JOIN account_account account ON account.id = line.account_id
          LEFT JOIN account_config config ON config.company_id = line.company_id
    ),
    counts AS (
        SELECT payment_id,
               COUNT(*) FILTER (WHERE guess = 'liquidity') AS n_liquidity,
               COUNT(*) FILTER (WHERE guess = 'counterpart') AS n_counterpart,
               COUNT(*) FILTER (WHERE guess = 'other') AS n_other
          FROM guess
         GROUP BY payment_id
    )
    SELECT guess.payment_id,
           guess.line_id,
           CASE
               WHEN guess.guess = 'other' AND counts.n_other = 1 AND counts.n_liquidity = 0
                   THEN 'liquidity'
               WHEN guess.guess = 'other' AND counts.n_other = 1 AND counts.n_counterpart = 0
                   THEN 'counterpart'
               WHEN guess.guess = 'other' THEN 'write_off'
               ELSE guess.guess
           END AS role
      FROM guess
      JOIN counts USING (payment_id)
""")

_UNCLASSIFIABLE_PAYMENTS = SQL("""
    SELECT role.payment_id, move.name,
           COUNT(*) FILTER (WHERE role.role = 'liquidity'),
           COUNT(*) FILTER (WHERE role.role = 'counterpart')
      FROM payarch_payment_line_role role
      JOIN account_payment payment ON payment.id = role.payment_id
      JOIN account_move move ON move.id = payment.move_id
     GROUP BY role.payment_id, move.name
    HAVING COUNT(*) FILTER (WHERE role.role = 'liquidity') <> 1
        OR COUNT(*) FILTER (WHERE role.role = 'counterpart') <> 1
     ORDER BY role.payment_id
""")

_CLASSIFY_STATEMENT_LINES = SQL("""
    CREATE TEMP TABLE payarch_statement_line_role ON COMMIT DROP AS
    SELECT st_line.id AS st_line_id,
           line.id AS line_id,
           CASE
               WHEN line.account_id = journal.default_account_id THEN 'liquidity'
               WHEN line.account_id = journal.suspense_account_id THEN 'suspense'
           END AS role
      FROM account_bank_statement_line st_line
      JOIN account_move move ON move.id = st_line.move_id
      JOIN account_journal journal ON journal.id = move.journal_id
      JOIN account_move_line line ON line.move_id = move.id
""")

_UNCLASSIFIABLE_STATEMENT_LINES = SQL("""
    SELECT role.st_line_id, move.name,
           COUNT(*) FILTER (WHERE role.role = 'liquidity'),
           COUNT(*) FILTER (WHERE role.role = 'suspense')
      FROM payarch_statement_line_role role
      JOIN account_bank_statement_line st_line ON st_line.id = role.st_line_id
      JOIN account_move move ON move.id = st_line.move_id
     GROUP BY role.st_line_id, move.name
    HAVING COUNT(*) FILTER (WHERE role.role = 'liquidity') <> 1
        OR COUNT(*) FILTER (WHERE role.role = 'suspense') > 1
     ORDER BY role.st_line_id
""")


def _add_column(cr, table, column, column_type):
    cr.execute(
        SQL(
            "ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s",
            SQL.identifier(table),
            SQL.identifier(column),
            column_type,
        )
    )


def _abort_if_any(rows, what, second_role):
    if rows:
        listing = "\n".join(
            f"  id {row[0]} ({row[1]}): {row[2]} liquidity, {row[3]} {second_role}"
            for row in rows
        )
        raise RuntimeError(
            f"account 1.42: {len(rows)} {what} cannot be given line roles; "
            f"fix their entries first:\n{listing}"
        )


def migrate(cr, version):
    if not version:
        return
    _add_column(cr, "account_move_line", "payment_role", SQL("varchar"))
    _add_column(cr, "account_payment", "counterpart_account_source", SQL("varchar"))
    _add_column(cr, "account_payment", "counterpart_review_required", SQL("boolean"))

    cr.execute(_CLASSIFY_PAYMENT_LINES)
    cr.execute(_UNCLASSIFIABLE_PAYMENTS)
    _abort_if_any(cr.fetchall(), "payment entries", "counterpart")
    cr.execute(
        """
        UPDATE account_move_line line
           SET payment_role = role.role
          FROM payarch_payment_line_role role
         WHERE line.id = role.line_id
        """
    )
    _logger.info("account 1.42: %s payment journal items got their role", cr.rowcount)

    cr.execute(_CLASSIFY_STATEMENT_LINES)
    cr.execute(_UNCLASSIFIABLE_STATEMENT_LINES)
    _abort_if_any(cr.fetchall(), "bank transactions", "suspense")
    cr.execute(
        """
        UPDATE account_move_line line
           SET payment_role = role.role
          FROM payarch_statement_line_role role
         WHERE line.id = role.line_id AND role.role IS NOT NULL
        """
    )
    _logger.info(
        "account 1.42: %s bank transaction journal items got their role", cr.rowcount
    )
