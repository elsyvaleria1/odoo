import uuid

from odoo import api, models
from odoo.fields import Domain


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _payment_request_from_kiosk(self, order):
        if self.use_payment_terminal != "razorpay":
            return super()._payment_request_from_kiosk(order)
        reference_prefix = order.config_id.name.replace(" ", "")
        reference = f"{reference_prefix}/Order/{order.id}/{uuid.uuid4().hex}"
        response = self.razorpay_make_payment_request(
            {
                "amount": order.currency_id.round(order.amount_total),
                "referenceId": reference,
            }
        )
        if response.get("p2pRequestId"):
            order._set_kiosk_terminal_request(reference, response["p2pRequestId"])
        return response

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        domain = super()._load_pos_self_data_domain(data, config)
        if config.self_ordering_mode == "kiosk":
            domain = Domain.OR(
                [
                    [
                        ("use_payment_terminal", "=", "razorpay"),
                        ("id", "in", config.payment_method_ids.ids),
                    ],
                    domain,
                ]
            )
        return domain
