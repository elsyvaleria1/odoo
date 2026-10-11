from odoo import api, fields, models


class WizardAccountPaymentCreateBatchPartial(models.TransientModel):
    _name = "wizard.account.payment.create.batch.partial"
    _description = "Create Batch Payment Error Wizard"

    payment_ids = fields.Many2many(
        comodel_name="account.payment",
        string="Payments",
        required=True,
    )
    error_message = fields.Char(compute="_compute_error_message")
    has_valid_payments = fields.Boolean(compute="_compute_has_valid_payments")

    def _compute_error_message(self) -> None:
        for wizard in self:
            is_accounting_installed = (
                self.env["account.move"]._get_invoice_in_payment_state() == "in_payment"
            )
            valid_states = (
                self.env._('"In Process"')
                if is_accounting_installed
                else self.env._('"In Process, and Paid"')
            )
            wizard.error_message = self.env._(
                "Only %s payments can be added to a batch. Invalid ones will be ignored.",
                valid_states,
            )

    @api.depends("payment_ids")
    def _compute_has_valid_payments(self) -> None:
        for wizard in self:
            valid_payment_states = self.env[
                "account.batch.payment"
            ]._valid_payment_states()
            wizard.has_valid_payments = any(
                payment.state in valid_payment_states for payment in wizard.payment_ids
            )

    def action_view_invalid_payments(self):
        valid_payment_states = self.env["account.batch.payment"]._valid_payment_states()
        invalid_payments = self.payment_ids.filtered(
            lambda p: p.state not in valid_payment_states
        )
        return invalid_payments._get_records_action(name=self.env._("Invalid Payments"))

    def action_create_batch(self):
        valid_payment_states = self.env["account.batch.payment"]._valid_payment_states()
        payments = self.payment_ids.filtered(lambda p: p.state in valid_payment_states)
        return payments.create_batch_payment()
