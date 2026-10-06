from odoo import fields, models


class WizardAccountBatchPaymentValidateErrorLine(models.TransientModel):
    _name = "wizard.account.batch.payment.validate.error.line"
    _description = "Batch payments error reporting wizard line"

    description = fields.Char(required=True)
    help_message = fields.Char(string="Help")
    payment_ids = fields.Many2many(
        comodel_name="account.payment",
        relation="account_batch_error_wizard_line_account_payment_rel",
        string="Payments",
        required=True,
    )
    error_wizard_id = fields.Many2one(
        comodel_name="wizard.account.batch.payment.validate.error"
    )
    warning_wizard_id = fields.Many2one(
        comodel_name="wizard.account.batch.payment.validate.error"
    )
    # Whether or not this line should display a button allowing to remove its related payments from the batch
    show_remove_button = fields.Boolean(compute="_compute_show_remove_button")

    def _compute_show_remove_button(self) -> None:
        for record in self:
            record.show_remove_button = (
                record.error_wizard_id.show_remove_options
                or record.warning_wizard_id.show_remove_options
            )

    def open_payments(self):
        return self.payment_ids._get_records_action(
            name=self.env._("Payments in Error")
        )

    def remove_payments_from_batch(self):
        for payment in self.payment_ids:
            payment.batch_payment_id = None

        # We try revalidating the batch if we still have payments for it (we hence do nothing for empty batches)
        batch = (self.error_wizard_id or self.warning_wizard_id).batch_payment_id
        if batch.payment_ids:
            return batch.confirm_batch()
        return None
