from odoo import Command, api, fields, models


class WizardAccountBatchPaymentValidateError(models.TransientModel):
    _name = "wizard.account.batch.payment.validate.error"
    _description = "Batch payments error reporting wizard"

    batch_payment_id = fields.Many2one(
        comodel_name="account.batch.payment",
        required=True,
        help="The batch payment generating the errors and warnings displayed in this wizard.",
    )
    error_line_ids = fields.One2many(
        comodel_name="wizard.account.batch.payment.validate.error.line",
        inverse_name="error_wizard_id",
    )
    warning_line_ids = fields.One2many(
        comodel_name="wizard.account.batch.payment.validate.error.line",
        inverse_name="warning_wizard_id",
    )
    show_remove_options = fields.Boolean(
        required=True,
        help="True if and only if the options to remove the payments causing the errors or warnings from the batch should be shown",
    )

    @api.model
    def create_from_errors_list(self, batch, errors_list, warnings_list):
        rslt = self.create(
            {"batch_payment_id": batch.id, "show_remove_options": batch.export_file}
        )
        self._create_error_wizard_lines(rslt.id, "error_wizard_id", errors_list)
        self._create_error_wizard_lines(rslt.id, "warning_wizard_id", warnings_list)
        return rslt

    @api.model
    def _create_error_wizard_lines(self, wizard_id, wizard_link_field, entries) -> None:
        wizard_line = self.env["wizard.account.batch.payment.validate.error.line"]
        wizard_line.create(
            [
                {
                    wizard_link_field: wizard_id,
                    "description": entry["title"],
                    "help_message": entry.get("help", None),
                    "payment_ids": [Command.set(entry["records"].ids)],
                }
                for entry in entries
            ]
        )

    def proceed_with_validation(self):
        self.check_singleton()
        return self.batch_payment_id._send_after_validation()
