import re
from collections import defaultdict
from datetime import UTC, datetime

from odoo import api, models
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)


class KpiProvider(models.AbstractModel):
    _inherit = "kpi.provider"

    @api.model
    def get_account_kpi_summary(self):
        self.env["account.move"].flush_model(
            ["state", "checked", "journal_id", "statement_line_id"]
        )
        self.env["account.bank.statement.line"].flush_model(["is_reconciled"])
        return get_kpi_summary(self.env.cr, self.env.uid)

    @api.model
    def get_account_reports_kpi_summary(self):
        return get_tax_return_kpi_summary(self.env.cr, self.env.uid)

    @api.model
    def get_kpi_summary(self):
        result = super().get_kpi_summary()
        result.extend(self.get_account_kpi_summary())
        result.extend(self.get_account_reports_kpi_summary())
        return result


def get_kpi_summary(cr, uid):
    expected_columns = {
        "account_bank_statement_line.is_reconciled",
        "account_move.checked",
        "account_move.journal_id",
        "account_move.state",
        "account_move.statement_line_id",
        "account_journal.type",
    }
    cr.execute(
        SQL(
            """
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE table_name || '.' || column_name IN %(columns)s
    """,
            columns=tuple(expected_columns),
        )
    )
    existing_columns = {x[0] for x in cr.fetchall()}
    if _debug.logic.enabled:
        _debug.logic(
            "kpi_columns_checked",
            uid=uid,
            missing=sorted(expected_columns - existing_columns),
        )
    if expected_columns - existing_columns:
        return []

    cr.execute(
        SQL(
            """
        WITH journal_type_selection AS (
            SELECT selection.value, COALESCE(selection.name->>p.lang, selection.name->>'en_US') name
              FROM ir_model_fields_selection selection
              JOIN ir_model_fields field ON selection.field_id = field.id
              JOIN res_users u ON u.id = %(uid)s
              JOIN res_partner p ON u.partner_id = p.id
             WHERE field.model = 'account.journal'
               AND field.name = 'type'
        )
        SELECT journal.type,
               COALESCE(journal_type_selection.name, journal.type),
               COUNT(*)
          FROM account_move move
          JOIN account_journal journal ON move.journal_id = journal.id
     LEFT JOIN account_bank_statement_line st_line ON move.statement_line_id = st_line.id
     LEFT JOIN journal_type_selection ON journal_type_selection.value = journal.type
         WHERE (   move.state = 'draft'
                OR (    move.state = 'posted'
                    AND NOT move.checked)
                OR (    move.state = 'posted'
                    AND journal.type = 'bank'
                    AND (st_line.id IS NULL OR NOT st_line.is_reconciled)))
      GROUP BY journal.type, journal_type_selection.name
    """,
            uid=uid,
        )
    )
    _debug.perf.count("kpi_journal_rows_fetched", rows=cr.rowcount)

    return [
        {
            "id": f"account_journal_type.{journal_type}",
            "name": journal_type_name,
            "type": "integer",
            "value": count,
        }
        for journal_type, journal_type_name, count in cr.fetchall()
    ]


def _tax_return_grouping_key(external_ids, return_info):
    external_id = ""

    external_id = external_ids.get(("report.formula", return_info["root_report_id"]))
    if not external_id:
        external_id = external_ids.get(("report.formula", return_info["report_id"]))
    if not external_id:
        external_id = external_ids.get(
            ("account.return.type", return_info["return_type_id"])
        )
    if not external_id:
        external_id = return_info["tax_return_name"]

    if external_id.startswith("l10n_eu_oss_reports."):
        external_id = "l10n_eu_oss_reports"

    return re.sub(r"[^a-z0-9_]", "_", external_id.lower())


def _tax_returns_get_value(tax_returns) -> str:
    for tax_return in tax_returns:
        if tax_return["is_late"]:
            return "late"
        elif not tax_return["is_completed"]:
            if tax_return["state"] in ("reviewed", "submitted"):
                return "to_submit"
            elif tax_return["in_next_3_months"]:
                return "to_do"
            else:
                return "longterm"
    return "done"


def get_tax_return_kpi_summary(cr, uid):
    expected_columns = {
        "account_return.date_deadline",
        "account_return.is_completed",
        "account_return.type_id",
        "account_return_type.report_id",
        "report_formula.root_report_id",
    }
    cr.execute(
        SQL(
            """
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE table_name || '.' || column_name IN %(columns)s
    """,
            columns=tuple(expected_columns),
        )
    )
    existing_columns = {x[0] for x in cr.fetchall()}
    if _debug.logic.enabled:
        _debug.logic(
            "tax_return_kpi_columns_checked",
            uid=uid,
            missing=sorted(expected_columns - existing_columns),
        )
    if expected_columns - existing_columns:
        return []

    cr.execute(
        SQL("""
        SELECT model, res_id, module || '.' || name
          FROM ir_model_data
         WHERE model IN ('report.formula', 'account.return.type')
           AND module != '__export__'
    """)
    )
    external_ids = {
        (model, res_id): complete_name for model, res_id, complete_name in cr.fetchall()
    }
    _debug.perf.count("tax_return_external_ids_fetched", rows=len(external_ids))

    cr.execute(
        SQL(
            """
        SELECT partner.tz
          FROM res_users u
          JOIN res_partner partner ON partner.id = u.partner_id
         WHERE u.id = %(uid)s
    """,
            uid=uid,
        )
    )
    row = cr.fetchone()
    today = datetime.now(UTC).astimezone(timezone((row and row[0]) or "UTC")).date()
    _debug.logic(
        "tax_return_kpi_today",
        uid=uid,
        tz=(row and row[0]) or "UTC",
        today=today,
        external_ids=len(external_ids),
    )
    cr.execute(
        SQL(
            """
        SELECT return.id return_id,
               type.id return_type_id,
               report.id report_id,
               root_report.id root_report_id,
               COALESCE(report.name->>partner.lang,
                        report.name->>'en_US',
                        type.name->>partner.lang,
                        type.name->>'en_US') tax_return_name,
               return.date_deadline <= %(today)s is_late,
               return.date_deadline <= %(today)s + INTERVAL '3 months' in_next_3_months,
               return.is_completed,
               return.state
          FROM account_return return
          JOIN res_users u ON u.id = %(uid)s
          JOIN res_partner partner ON partner.id = u.partner_id
          JOIN account_return_type type ON return.type_id = type.id
     LEFT JOIN report_formula report ON type.report_id = report.id
     LEFT JOIN report_formula root_report ON report.root_report_id = root_report.id
         WHERE (NOT return.is_completed
               OR return.date_deadline >= %(today)s)
               AND EXISTS (
                   SELECT 1
                     FROM account_return_res_company_rel arc
                     JOIN res_company_users_rel rcu
                       ON rcu.cid = arc.res_company_id
                    WHERE arc.account_return_id = return.id
                      AND rcu.user_id = %(uid)s
               )
      ORDER BY return.date_deadline NULLS LAST, return.id
    """,
            uid=uid,
            today=today,
        )
    )
    returns_by_external_id = defaultdict(list)
    for return_info in cr.dictfetchall():
        key = _tax_return_grouping_key(external_ids, return_info)
        returns_by_external_id[key].append(return_info)
    if _debug.pipeline.enabled:
        _debug.pipeline(
            "tax_returns_grouped",
            uid=uid,
            groups=len(returns_by_external_id),
            returns=sum(len(returns) for returns in returns_by_external_id.values()),
        )

    return [
        {
            "id": f"account_return.{external_id}",
            "name": tax_returns[0]["tax_return_name"],
            "type": "return_status",
            "value": _tax_returns_get_value(tax_returns),
        }
        for external_id, tax_returns in returns_by_external_id.items()
    ]
