import csv
import logging
import re
from pathlib import Path

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL, config

_logger = logging.getLogger(__name__)

REPORT_COLUMNS = (
    "finding",
    "kind",
    "action",
    "model",
    "res_id",
    "company_id",
    "period",
    "amount",
    "detail",
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _report_line_dates(cr)
    _report_name_periods(env)
    _report_due_dates(cr)
    _report_duplicate_names(cr)
    _write_report(cr)


def _report_line_dates(cr) -> None:
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F10', 'line_date', 'accountant', 'account.move.line', line.id, line.company_id,
               to_char(move.date, 'YYYY-MM'), line.balance,
               CONCAT(move.name, ' (', move.move_type, ') dated ', move.date, ', line dated ', line.date)
          FROM account_move_line line
          JOIN account_move move ON move.id = line.move_id
         WHERE move.state = 'posted' AND line.date != move.date
        """
    )


def _report_name_periods(env) -> None:
    cr = env.cr
    Move = env["account.move"]
    monthly = re.compile(Move._sequence_monthly_regex)
    yearly = re.compile(Move._sequence_yearly_regex)
    cr.execute(
        """
        SELECT id, company_id, name, date
          FROM account_move
         WHERE state = 'posted' AND name IS NOT NULL AND name != '/'
        """
    )
    rows = []
    for move_id, company_id, name, date in cr.fetchall():
        if match := monthly.match(name):
            named = (_full_year(match["year"], date.year), int(match["month"]))
            dated = (date.year, date.month)
        elif match := yearly.match(name):
            named, dated = (_full_year(match["year"], date.year),), (date.year,)
        else:
            continue
        if named != dated and 2000 <= named[0] < 2100:
            rows.append(
                (
                    "F14",
                    "name_period",
                    "accountant",
                    "account.move",
                    move_id,
                    company_id,
                    date.strftime("%Y-%m"),
                    None,
                    f"{name} dated {date}",
                )
            )
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


def _full_year(year: str, reference: int) -> int:
    return int(year) if len(year) == 4 else reference // 100 * 100 + int(year)


def _report_due_dates(cr) -> None:
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F15', 'invoice_date_due', 'report', 'account.move', move.id, move.company_id,
               to_char(move.date, 'YYYY-MM'), NULL,
               CONCAT(move.name, ': due ', move.invoice_date_due, ', latest term maturity ', term.maturity)
          FROM account_move move
          JOIN (
                SELECT move_id, MAX(date_maturity) AS maturity
                  FROM account_move_line
                 WHERE display_type = 'payment_term'
              GROUP BY move_id
               ) term ON term.move_id = move.id
         WHERE move.state = 'posted'
           AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
           AND move.invoice_date_due IS DISTINCT FROM term.maturity
        """
    )


def _report_duplicate_names(cr) -> None:
    cr.execute(
        """
        INSERT INTO account_repair_141_report
               (finding, kind, action, model, res_id, company_id, period, amount, detail)
        SELECT 'F4', 'duplicate_name', 'accountant', 'account.move', move.id, move.company_id,
               to_char(move.date, 'YYYY-MM'), move.amount_total_signed,
               CONCAT(move.name, ' (', move.state, ', journal ', journal.code, ', dated ', move.date, ')')
          FROM account_move move
          JOIN account_journal journal ON journal.id = move.journal_id
         WHERE (move.company_id, move.name) IN (
                SELECT company_id, name
                  FROM account_move
                 WHERE name IS NOT NULL AND name != '/'
              GROUP BY company_id, name
                HAVING COUNT(*) > 1
               )
        """
    )


def _write_report(cr) -> None:
    cr.execute(
        """
        SELECT finding, kind, action, COUNT(DISTINCT (model, res_id)), SUM(amount)
          FROM account_repair_141_report
      GROUP BY finding, kind, action
      ORDER BY finding, kind, action
        """
    )
    summary = cr.fetchall()
    _logger.info("account 1.41 repair report: %s class(es)", len(summary))
    for finding, kind, action, count, amount in summary:
        _logger.info(
            "account 1.41 repair report: %-6s %-26s %-10s %7s record(s)%s",
            finding,
            kind,
            action,
            count,
            f", amount {amount}" if amount is not None else "",
        )
    cr.execute(
        """
        SELECT finding, kind, model, ARRAY_AGG(res_id ORDER BY res_id)
          FROM account_repair_141_report
         WHERE action = 'accountant'
      GROUP BY finding, kind, model
      ORDER BY finding, kind
        """
    )
    for finding, kind, model, ids in cr.fetchall():
        _logger.info(
            "account 1.41 repair report: for the accountant, %s %s (%s %s): %s",
            finding,
            kind,
            len(ids),
            model,
            ids if len(ids) <= 200 else f"{ids[:200]} and {len(ids) - 200} more",
        )
    cr.execute(
        SQL(
            "SELECT %s FROM account_repair_141_report ORDER BY id",
            SQL(", ").join(SQL.identifier(column) for column in REPORT_COLUMNS),
        )
    )
    path = Path(
        config["data_dir"], "upgrade_reports", f"{cr.dbname}-account-1.41-repair.csv"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as report:
        writer = csv.writer(report)
        writer.writerow(REPORT_COLUMNS)
        writer.writerows(cr.fetchall())
    _logger.info("account 1.41 repair report: every row written to %s", path)
    cr.execute("DROP TABLE account_repair_141_report")
