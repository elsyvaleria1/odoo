from odoo import fields, models


class PaymentToken(models.Model):
    _inherit = "payment.token"

    sdd_mandate_id = fields.Many2one(
        comodel_name="sdd.mandate",
        string="SEPA Direct Debit Mandate",
        readonly=True,
        ondelete="set null",
    )

    def _prepare_display_name(self, *args, max_length=34, should_pad=True, **kwargs):
        payment_details = super()._prepare_display_name(
            *args, max_length=max_length, should_pad=should_pad, **kwargs
        )
        if self.provider_id.custom_mode != "sepa_direct_debit":
            return payment_details

        if len(self.payment_details) <= max_length:
            return super()._prepare_display_name(
                *args, max_length=max_length, should_pad=False, **kwargs
            )
        else:
            return f"{self.payment_details[:2]}*{self.payment_details[-4:]}"
