from odoo import api, fields, models


class AccountImportSummary(models.TransientModel):
    _name = "wizard.account.import.summary"
    _description = "Account import summary view"
    _rec_name = "import_summary_name"

    import_summary_account_ids = fields.Many2many(comodel_name="account.account")
    import_summary_journal_ids = fields.Many2many(comodel_name="account.journal")
    import_summary_move_ids = fields.Many2many(comodel_name="account.move")
    import_summary_partner_ids = fields.Many2many(comodel_name="res.partner")
    import_summary_tax_ids = fields.Many2many(comodel_name="account.tax")

    import_summary_name = fields.Char(default="Import Summary")
    import_summary_len_account = fields.Count(
        count_of="import_summary_account_ids",
        export_string_translation=False,
    )
    import_summary_len_journal = fields.Count(
        count_of="import_summary_journal_ids",
        export_string_translation=False,
    )
    import_summary_len_move = fields.Count(
        count_of="import_summary_move_ids",
        export_string_translation=False,
    )
    import_summary_len_partner = fields.Count(
        count_of="import_summary_partner_ids",
        export_string_translation=False,
    )
    import_summary_len_tax = fields.Count(
        count_of="import_summary_tax_ids",
        export_string_translation=False,
    )
    import_summary_have_data = fields.Boolean(
        export_string_translation=False,
        compute="_compute_import_summary_have_data",
    )

    @api.depends(
        "import_summary_account_ids",
        "import_summary_journal_ids",
        "import_summary_move_ids",
        "import_summary_partner_ids",
        "import_summary_tax_ids",
    )
    def _compute_import_summary_have_data(self) -> None:
        for record in self:
            record.import_summary_have_data = bool(
                record.import_summary_account_ids
                or record.import_summary_journal_ids
                or record.import_summary_move_ids
                or record.import_summary_partner_ids
                or record.import_summary_tax_ids
            )

    def action_view_summary_view(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Import Summary"),
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "view_mode": "form",
            "res_model": "wizard.account.import.summary",
        }

    def action_view_account_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account_base_import.action_open_coa_setup"
        )
        action["domain"] = [("id", "in", self.import_summary_account_ids.ids)]
        return action

    def action_view_journal_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.action_account_journal_form"
        )
        action["domain"] = [("id", "in", self.import_summary_journal_ids.ids)]
        return action

    def action_view_move_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.action_move_line_form"
        )
        action["domain"] = [("id", "in", self.import_summary_move_ids.ids)]
        return action

    def action_view_partner_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "base.action_partner_form"
        )
        action["domain"] = [("id", "in", self.import_summary_partner_ids.ids)]
        return action

    def action_view_tax_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.action_tax_form"
        )
        action["domain"] = [("id", "in", self.import_summary_tax_ids.ids)]
        return action
