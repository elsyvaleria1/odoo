from odoo import fields, models


class AccountReportLine(models.Model):
    _inherit = "report.formula.line"

    account_codes_formula = fields.Char(
        string="Account Codes Formula Shortcut",
        inverse="_inverse_account_codes_formula",
        store=False,
        copy=False,
        help="Internal field to shorten expression_ids creation for the account_codes engine",
    )
    tax_tags_formula = fields.Char(
        string="Tax Tags Formula Shortcut",
        inverse="_inverse_tax_tags_formula",
        store=False,
        copy=False,
        help="Internal field to shorten expression_ids creation for the tax_tags engine",
    )

    def _inverse_tax_tags_formula(self) -> None:
        self._create_report_expression(engine="tax_tags")

    def _inverse_account_codes_formula(self) -> None:
        self._create_report_expression(engine="account_codes")

    def _get_indenting_groupby_models(self) -> tuple:
        return ("account.group",)

    def _get_groupby_record_state(self, groupby_model, record):
        if groupby_model == "account.move.line":
            return record.parent_state
        if groupby_model == "account.move":
            return record.state
        return super()._get_groupby_record_state(groupby_model, record)

    def _get_shortcut_expression_formula(self, engine) -> tuple | None:
        if engine == "account_codes" and self.account_codes_formula:
            return None, self.account_codes_formula
        if engine == "tax_tags" and self.tax_tags_formula:
            return None, self.tax_tags_formula
        return super()._get_shortcut_expression_formula(engine)

    def _get_groupby(self, options):
        groupby = super()._get_groupby(options)
        if options["export_mode"] == "file":
            return groupby

        groupby_lst = [
            groupby.strip() for groupby in (self.user_groupby or "").split(",")
        ]
        if options["consolidation"] and "account_id" in groupby_lst:
            index_account_id = groupby_lst.index("account_id")
            groupby_lst.insert(index_account_id, "account_code")
            return ",".join(groupby_lst)
        return groupby
