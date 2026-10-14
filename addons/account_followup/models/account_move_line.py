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
        return SQL(
            "COALESCE(%(date_maturity)s, %(date)s) < %(current_date)s",
            date_maturity=self._field_to_sql(alias, "date_maturity", query),
            date=self._field_to_sql(alias, "date", query),
            current_date=SQL(
                "%s::date",
                SQL.literal(fields.Date.to_string(fields.Date.context_today(self))),
            ),
        )

    def _read_group_empty_value(self, spec):
        if spec != "followup_overdue":
            return super()._read_group_empty_value(spec)
        return False

    def _read_group_postprocess_groupby(self, groupby_spec, raw_values):
        if groupby_spec != "followup_overdue":
            return super()._read_group_postprocess_groupby(groupby_spec, raw_values)
        return ((value or False) for value in raw_values)
