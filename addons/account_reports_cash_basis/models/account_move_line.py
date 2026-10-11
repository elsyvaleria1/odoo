from odoo import api, models
from odoo.tools import SQL


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"
    _search_visibility_fields = ()

    @api.model
    def _search(self, *args, **kwargs):
        query = super()._search(*args, **kwargs)
        if self.env.context.get("account_report_cash_basis"):
            self.env["report.formula"]._prepare_lines_for_cash_basis()
            if self.env.context.get("account_report_analytic_groupby"):
                self.env[
                    "report.formula"
                ]._prepare_lines_for_analytic_groupby_with_cash_basis()
                query._tables["account_move_line"] = SQL.identifier(
                    "analytic_cash_basis_temp_account_move_line"
                )
            else:
                query._tables["account_move_line"] = SQL.identifier(
                    "cash_basis_temp_account_move_line"
                )
        return query
