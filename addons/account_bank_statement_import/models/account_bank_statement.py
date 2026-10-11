from markupsafe import Markup

from odoo import api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    unique_import_id = fields.Char(
        string="Import ID",
        copy=False,
        readonly=True,
    )

    _unique_import_id = models.Constraint(
        "unique (unique_import_id)",
        "A bank account transactions can be imported only once!",
    )

    @api.model
    def get_import_templates(self):
        return [
            {
                "label": self.env._("Import Template for Bank Statement Lines"),
                "template": "/account_bank_statement_import/static/xls/bank_statement_line_import_template.xlsx",
            }
        ]

    def _action_view_bank_reconciliation_widget(
        self, extra_domain=None, default_context=None, name=None, kanban_first=True
    ):
        res = super()._action_view_bank_reconciliation_widget(
            extra_domain, default_context, name, kanban_first
        )
        formats_list = sorted(
            self.env["account.journal"]._get_bank_statements_available_import_formats()
        )
        upload_sentence = (
            self.env._('Click "New" or upload a %s.', ", ".join(formats_list))
            if formats_list
            else self.env._('Click "New" or upload a file.')
        )
        res["help"] = Markup(
            "<p class='o_view_nocontent_smiling_face'>{}</p><p>{}<br/>{}</p>"
        ).format(
            self.env._("Nothing to do here!"),
            self.env._("No transactions matching your filters were found."),
            upload_sentence,
        )
        return res
