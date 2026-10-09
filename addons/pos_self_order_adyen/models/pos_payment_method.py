import logging
import random
from datetime import UTC, datetime

from odoo import api, fields, models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _adyen_settle(self, data, pending, state) -> None:
        self_order_id = pending.get("self_order_id")
        if not self_order_id:
            super()._adyen_settle(data, pending, state)
            return
        order_sudo = self.env["pos.order"].sudo().browse(self_order_id).exists()
        if not order_sudo or order_sudo.config_id.self_ordering_mode != "kiosk":
            _logger.warning(
                "Adyen settled request %s for the kiosk order #%s, which is gone",
                pending["service_id"],
                self_order_id,
            )
            return
        payment_response = data["SaleToPOIResponse"]["PaymentResponse"]
        if state == "confirmed":
            order = order_sudo.with_user(
                order_sudo.session_id.config_id.self_ordering_default_user_id
            ).with_company(order_sudo.session_id.config_id.company_id)
            payment_result = payment_response["PaymentResult"]
            order.add_payment(
                {
                    "amount": payment_result["AmountsResp"]["AuthorizedAmount"],
                    "payment_date": fields.Datetime.now(),
                    "payment_method_id": self.id,
                    "card_type": payment_result["PaymentInstrumentData"]["CardData"][
                        "PaymentBrand"
                    ],
                    "cardholder_name": "",
                    "transaction_id": payment_response["SaleData"]["SaleTransactionID"][
                        "TransactionID"
                    ],
                    "payment_status": "Success",
                    "ticket": "",
                    "pos_order_id": order.id,
                }
            )
            order.action_pos_order_paid()
            order_sudo._send_payment_result("Success")
        elif state == "unconfirmed":
            _logger.warning(
                "Adyen could not confirm the approval of kiosk order %s: check "
                "the terminal before taking another payment for it",
                order_sudo.pos_reference,
            )
            order_sudo._send_payment_result("unconfirmed")
        else:
            order_sudo._send_payment_result(payment_response["Response"]["Result"])

    def _payment_request_from_kiosk(self, order):
        if self.use_payment_terminal != "adyen":
            return super()._payment_request_from_kiosk(order)
        else:
            pos_config = order.session_id.config_id
            random_number = random.randrange(10**9, 10**10 - 1)

            # https://docs.adyen.com/point-of-sale/basic-tapi-integration/make-a-payment/#make-a-payment
            data = {
                "SaleToPOIRequest": {
                    "MessageHeader": {
                        "ProtocolVersion": "3.0",
                        "MessageClass": "Service",
                        "MessageType": "Request",
                        "MessageCategory": "Payment",
                        "SaleID": f"{pos_config.display_name} (ID:{pos_config.id})",  # 	Your unique ID for the POS system component to send this request from.
                        "ServiceID": str(
                            random_number
                        ),  # Your unique ID for this request, consisting of 1-10 alphanumeric characters.
                        "POIID": self.adyen_terminal_identifier,  # 	The unique ID of the terminal to send this request to.
                    },
                    "PaymentRequest": {
                        "SaleData": {
                            "SaleTransactionID": {
                                "TransactionID": order.pos_reference,  # your reference to identify a payment.
                                "TimeStamp": datetime.now(tz=UTC).isoformat(
                                    timespec="seconds"
                                ),  # date and time of the request in UTC format.
                            },
                        },
                        "PaymentTransaction": {
                            "AmountsReq": {
                                "Currency": order.currency_id.name,  # the transaction currency.
                                "RequestedAmount": order.amount_total,  # The final transaction amount.
                            },
                        },
                    },
                },
            }

            self._adyen_sign_payment_request(data, self_order_id=order.id)
            req = self._proxy_adyen_request_direct(data, "terminal_request")

            return req and (isinstance(req, bool) or not req.get("error"))

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        domain = super()._load_pos_self_data_domain(data, config)
        if config.self_ordering_mode == "kiosk":
            domain = Domain.OR(
                [
                    [
                        ("use_payment_terminal", "=", "adyen"),
                        ("id", "in", config.payment_method_ids.ids),
                    ],
                    domain,
                ]
            )
        return domain
