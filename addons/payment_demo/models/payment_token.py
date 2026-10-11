from odoo import fields, models


class PaymentToken(models.Model):
    _inherit = "payment.token"

    demo_simulated_state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("done", "Confirmed"),
            ("cancel", "Canceled"),
            ("error", "Error"),
        ],
        string="Simulated State",
        help="The state in which transactions created from this token should be set.",
    )

    def _prepare_display_name(self, *args, should_pad=True, **kwargs):
        if self.provider_code != "demo":
            return super()._prepare_display_name(*args, should_pad=should_pad, **kwargs)
        return super()._prepare_display_name(*args, should_pad=False, **kwargs)
