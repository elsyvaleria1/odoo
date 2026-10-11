import uuid

from odoo import api, models
from odoo.fields import Domain
from odoo.tools import float_round


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _payment_request_from_kiosk(self, order):
        if self.use_payment_terminal != "pine_labs":
            return super()._payment_request_from_kiosk(order)
        reference_prefix = order.config_id.name.replace(" ", "")
        data = {
            "amount": self._pine_labs_paisa(order),
            "transactionNumber": f"{reference_prefix}/Order/{order.id}/{uuid.uuid4().hex}",
            "sequenceNumber": "1",
        }
        payment_response = self.pine_labs_make_payment_request(data)
        if payment_response.get("plutusTransactionReferenceID"):
            order._set_kiosk_terminal_request(
                data["transactionNumber"],
                payment_response["plutusTransactionReferenceID"],
            )
        payment_response["payment_ref_no"] = data["transactionNumber"]
        return payment_response

    @api.model
    def _pine_labs_paisa(self, order) -> int:
        return int(
            float_round(
                order.amount_total * 10**order.currency_id.decimal_places,
                precision_digits=0,
            )
        )

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        domain = super()._load_pos_self_data_domain(data, config)
        if data["pos.config"][0]["self_ordering_mode"] == "kiosk":
            domain = Domain.OR(
                [
                    [
                        ("use_payment_terminal", "=", "pine_labs"),
                        ("id", "in", config.payment_method_ids.ids),
                    ],
                    domain,
                ]
            )
        return domain
