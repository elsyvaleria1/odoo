from odoo import api, fields, models


class AccountImportSummary(models.TransientModel):
    _inherit = "wizard.account.import.summary"

    import_summary_analytic_ids = fields.Many2many(
        comodel_name="account.analytic.account"
    )
    import_summary_analytic_line_ids = fields.Many2many(
        comodel_name="account.analytic.line"
    )

    import_summary_len_analytic = fields.Count(count_of="import_summary_analytic_ids")
    import_summary_len_analytic_line = fields.Count(
        count_of="import_summary_analytic_line_ids"
    )

    @api.depends("import_summary_analytic_ids", "import_summary_analytic_line_ids")
    def _compute_import_summary_have_data(self) -> None:
        # EXTENDS 'account_base_import'
        super()._compute_import_summary_have_data()
        for record in self:
            if not record.import_summary_have_data:
                record.import_summary_have_data = bool(
                    record.import_summary_analytic_ids
                    or record.import_summary_analytic_line_ids
                )

    def action_view_analytic_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "analytic.action_account_analytic_account_form"
        )
        action["domain"] = [("id", "in", self.import_summary_analytic_ids.ids)]
        return action

    def action_view_analytic_line_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "analytic.account_analytic_line_action_entries"
        )
        action["domain"] = [("id", "in", self.import_summary_analytic_line_ids.ids)]
        return action
