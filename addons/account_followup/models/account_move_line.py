from odoo import fields, models
from odoo.tools import SQL, Query


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    followup_line_id = fields.Many2one(
        comodel_name="account_followup.followup.line",
        string="Follow-up Level",
        copy=False,
    )

    def _read_group_groupby(self, alias: str, groupby_spec: str, query: Query) -> SQL:
        if groupby_spec != "followup_overdue":
            return super()._read_group_groupby(alias, groupby_spec, query)
        # current_date must be a SQL literal (not a bound parameter) because this
        # expression appears in both SELECT and GROUP BY. With psycopg3 server-side
        # binding, each bound param gets a unique $N — making PostgreSQL see them
        # as different expressions and reject the GROUP BY.
        return SQL(
            "%(date_maturity)s IS NOT NULL AND %(date_maturity)s < %(current_date)s",
            date_maturity=self._field_to_sql(self._table, "date_maturity", query),
            current_date=SQL("'%s'" % fields.Date.context_today(self)),  # pylint: disable=E8501 - server-computed date, not user input; see comment above
        )

    def _read_group_empty_value(self, spec):
        if spec != "followup_overdue":
            return super()._read_group_empty_value(spec)
        return False

    def _read_group_postprocess_groupby(self, groupby_spec, raw_values):
        if groupby_spec != "followup_overdue":
            return super()._read_group_postprocess_groupby(groupby_spec, raw_values)
        return ((value or False) for value in raw_values)
