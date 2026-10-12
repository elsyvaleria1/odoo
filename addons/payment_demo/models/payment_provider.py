from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.payment_demo import const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("demo", "Demo")],
        ondelete={"demo": "set default"},
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "demo").update(
            {
                "support_express_checkout": True,
                "support_manual_capture": "partial",
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )

    @api.constrains("state", "code")
    def _check_provider_state(self) -> None:
        if self.filtered(
            lambda p: p.code == "demo" and p.state not in ("test", "disabled")
        ):
            raise UserError(self.env._("Demo providers should never be enabled."))

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.code != "demo":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES
