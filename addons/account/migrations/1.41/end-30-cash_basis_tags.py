import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.flush_all()
    _collect_expected_tags(cr)
    _apply_expected_tags(env)
    for table in ("caba_141_tag_change", "caba_141_expected", "caba_141_line"):
        cr.execute(SQL("DROP TABLE %s", SQL.identifier(table)))


def _collect_expected_tags(cr) -> None:
    cr.execute(
        """
        CREATE TEMP TABLE caba_141_line AS
        SELECT line.id, line.move_id, line.company_id, line.date, line.balance, line.debit, line.credit,
               line.tax_repartition_line_id,
               origin.move_type AS origin_type,
               origin.reversed_entry_id IS NOT NULL AS origin_reversed
          FROM account_move move
          JOIN account_move origin ON origin.id = move.tax_cash_basis_origin_move_id
          JOIN account_move_line line ON line.move_id = move.id
         WHERE move.state IN ('posted', 'draft')
        """
    )
    cr.execute(
        """
        CREATE TEMP TABLE caba_141_expected AS
          WITH line_tax AS (
                SELECT caba.id, tax.id AS tax_id, tax.type_tax_use, tax.sequence
                  FROM caba_141_line caba
                  JOIN account_move_line_account_tax_rel rel ON rel.account_move_line_id = caba.id
                  JOIN account_tax tax ON tax.id = rel.account_tax_id
                 WHERE tax.tax_exigibility = 'on_payment'
          ), tax_use AS (
                SELECT id,
                       BOOL_OR(type_tax_use = 'sale') AND BOOL_OR(type_tax_use = 'purchase') AS mixed,
                       (ARRAY_AGG(type_tax_use ORDER BY sequence, tax_id))[1] AS first_use
                  FROM line_tax
              GROUP BY id
          ), side AS (
                -- _compute_is_refund of the origin line the cash-basis line copies
                SELECT caba.id,
                       CASE
                           WHEN caba.tax_repartition_line_id IS NOT NULL THEN rep.document_type = 'refund'
                           WHEN caba.origin_type IN ('out_refund', 'in_refund') THEN TRUE
                           WHEN caba.origin_type != 'entry' THEN FALSE
                           ELSE (CASE
                                     WHEN tax_use.mixed THEN caba.credit = 0
                                     ELSE (tax_use.first_use = 'sale' AND caba.credit = 0)
                                       OR (tax_use.first_use = 'purchase' AND caba.debit = 0)
                                 END) != caba.origin_reversed
                       END AS is_refund
                  FROM caba_141_line caba
                  JOIN tax_use ON tax_use.id = caba.id
             LEFT JOIN account_tax_repartition_line rep ON rep.id = caba.tax_repartition_line_id
          )
        SELECT line_tax.id AS line_id, tag_rel.account_account_tag_id AS tag_id
          FROM line_tax
          JOIN side ON side.id = line_tax.id
          JOIN account_tax_repartition_line rep
               ON rep.tax_id = line_tax.tax_id
              AND rep.repartition_type = 'base'
              AND rep.document_type = CASE WHEN side.is_refund THEN 'refund' ELSE 'invoice' END
          JOIN account_account_tag_account_tax_repartition_line_rel tag_rel
               ON tag_rel.account_tax_repartition_line_id = rep.id
         UNION
        SELECT caba.id, tag_rel.account_account_tag_id
          FROM caba_141_line caba
          JOIN account_account_tag_account_tax_repartition_line_rel tag_rel
               ON tag_rel.account_tax_repartition_line_id = caba.tax_repartition_line_id
        """
    )
    cr.execute(
        """
        CREATE TEMP TABLE caba_141_tag_change AS
          WITH to_fix AS (
                SELECT DISTINCT expected.line_id
                  FROM caba_141_expected expected
                 WHERE NOT EXISTS (
                        SELECT 1
                          FROM account_account_tag_account_move_line_rel rel
                         WHERE rel.account_move_line_id = expected.line_id
                           AND rel.account_account_tag_id = expected.tag_id
                       )
          )
        SELECT expected.line_id, expected.tag_id, 1 AS direction
          FROM caba_141_expected expected
          JOIN to_fix ON to_fix.line_id = expected.line_id
         WHERE NOT EXISTS (
                SELECT 1
                  FROM account_account_tag_account_move_line_rel rel
                 WHERE rel.account_move_line_id = expected.line_id
                   AND rel.account_account_tag_id = expected.tag_id
               )
         UNION ALL
        SELECT rel.account_move_line_id, rel.account_account_tag_id, -1
          FROM account_account_tag_account_move_line_rel rel
          JOIN to_fix ON to_fix.line_id = rel.account_move_line_id
          JOIN account_account_tag tag ON tag.id = rel.account_account_tag_id
         WHERE tag.applicability = 'taxes'
           AND NOT EXISTS (
                SELECT 1
                  FROM caba_141_expected expected
                 WHERE expected.line_id = rel.account_move_line_id
                   AND expected.tag_id = rel.account_account_tag_id
               )
        """
    )


def _apply_expected_tags(env) -> None:
    cr = env.cr
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F9', 'cash_basis_tags', 'fixed', 'account.move.line', caba.id, caba.company_id,
               to_char(caba.date, 'YYYY'), caba.balance,
               CONCAT(CASE WHEN caba.tax_repartition_line_id IS NULL THEN 'base' ELSE 'tax' END,
                      ' line of ', move.name,
                      ': +', STRING_AGG(tag.name->>'en_US', ', ' ORDER BY tag.id)
                                FILTER (WHERE change.direction = 1),
                      COALESCE(' -' || STRING_AGG(tag.name->>'en_US', ', ' ORDER BY tag.id)
                                FILTER (WHERE change.direction = -1), ''))
          FROM caba_141_tag_change change
          JOIN caba_141_line caba ON caba.id = change.line_id
          JOIN account_move move ON move.id = caba.move_id
          JOIN account_account_tag tag ON tag.id = change.tag_id
      GROUP BY caba.id, caba.company_id, caba.date, caba.balance, caba.tax_repartition_line_id, move.name
        """
    )
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F9', 'tax_report_delta', 'report', 'account.account.tag', tag.id, caba.company_id,
               to_char(caba.date, 'YYYY'), SUM(change.direction * caba.balance),
               CONCAT(tag.name->>'en_US', ': ', COUNT(*), ' line(s) ',
                      CASE WHEN change.direction = 1 THEN 'gain' ELSE 'lose' END, ' the tag')
          FROM caba_141_tag_change change
          JOIN caba_141_line caba ON caba.id = change.line_id
          JOIN account_account_tag tag ON tag.id = change.tag_id
      GROUP BY tag.id, caba.company_id, to_char(caba.date, 'YYYY'), change.direction
        """
    )
    cr.execute(
        """
        DELETE FROM account_account_tag_account_move_line_rel rel
         USING caba_141_tag_change change
         WHERE change.direction = -1
           AND rel.account_move_line_id = change.line_id
           AND rel.account_account_tag_id = change.tag_id
        """
    )
    removed = cr.rowcount
    cr.execute(
        """
        INSERT INTO account_account_tag_account_move_line_rel (account_move_line_id, account_account_tag_id)
        SELECT line_id, tag_id FROM caba_141_tag_change WHERE direction = 1
        """
    )
    added = cr.rowcount
    env["account.move.line"].invalidate_model(["tax_tag_ids"])
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F9', 'unexpected_tag', 'report', 'account.move.line', caba.id, caba.company_id,
               to_char(caba.date, 'YYYY'), caba.balance,
               CONCAT(move.name, ': ', tag.name->>'en_US',
                      ' is not a tag the cash-basis code gives this line')
          FROM account_account_tag_account_move_line_rel rel
          JOIN caba_141_line caba ON caba.id = rel.account_move_line_id
          JOIN account_move move ON move.id = caba.move_id
          JOIN account_account_tag tag ON tag.id = rel.account_account_tag_id
         WHERE tag.applicability = 'taxes'
           AND NOT EXISTS (
                SELECT 1
                  FROM caba_141_expected expected
                 WHERE expected.line_id = rel.account_move_line_id
                   AND expected.tag_id = rel.account_account_tag_id
               )
        """
    )
    cr.execute(
        """
        SELECT COUNT(DISTINCT change.line_id),
               COUNT(DISTINCT change.line_id) FILTER (WHERE caba.tax_repartition_line_id IS NOT NULL),
               COUNT(DISTINCT caba.move_id)
          FROM caba_141_tag_change change
          JOIN caba_141_line caba ON caba.id = change.line_id
        """
    )
    lines, tax_lines, moves = cr.fetchone()
    if lines:
        _logger.info(
            "account: %s cash-basis journal item(s) (%s tax, %s base) of %s entr(ies) take their "
            "repartition tags: %s tag(s) added, %s replaced",
            lines,
            tax_lines,
            lines - tax_lines,
            moves,
            added,
            removed,
        )
    cr.execute(
        """
        SELECT caba.company_id, to_char(caba.date, 'YYYY'),
               SUM(caba.balance) FILTER (WHERE caba.tax_repartition_line_id IS NOT NULL),
               SUM(caba.balance) FILTER (WHERE caba.tax_repartition_line_id IS NULL)
          FROM caba_141_line caba
         WHERE caba.id IN (SELECT line_id FROM caba_141_tag_change WHERE direction = 1)
      GROUP BY 1, 2
      ORDER BY 1, 2
        """
    )
    for company_id, year, tax_amount, base_amount in cr.fetchall():
        _logger.info(
            "account: company %s, %s: cash-basis tax %s and base %s newly reach the tag-based tax report",
            company_id,
            year,
            tax_amount or 0,
            base_amount or 0,
        )
