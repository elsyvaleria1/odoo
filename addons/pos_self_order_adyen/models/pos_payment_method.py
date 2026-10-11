import logging
import random
from datetime import UTC, datetime
from urllib.parse import parse_qs

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
                "Adyen could not confirm the approval of kiosk order %s: it waits "
                "for staff to check the terminal",
                order_sudo.pos_reference,
            )
            additional = parse_qs(payment_response["Response"]["AdditionalResponse"])
            order_sudo._hold_kiosk_payment_to_verify(
                self,
                payment_response["PaymentResult"]["AmountsResp"]["AuthorizedAmount"],
                (additional.get("pspReference") or [""])[0],
            )
        else:
            order_sudo._send_payment_result(payment_response["Response"]["Result"])

    def _payment_request_from_kiosk(self, order):
        if self.use_payment_terminal != "adyen":
            return super()._payment_request_from_kiosk(order)
        else:
            pos_config = order.session_id.config_id
            random_number = random.randrange(10**9, 10**10 - 1)

            data = {
                "SaleToPOIRequest": {
                    "MessageHeader": {
                        "ProtocolVersion": "3.0",
                        "MessageClass": "Service",
                        "MessageType": "Request",
                        "MessageCategory": "Payment",
                        "SaleID": f"{pos_config.display_name} (ID:{pos_config.id})",
                        "ServiceID": str(
                            random_number
                        ),
                        "POIID": self.adyen_terminal_identifier,
                    },
                    "PaymentRequest": {
                        "SaleData": {
                            "SaleTransactionID": {
                                "TransactionID": order.pos_reference,
                                "TimeStamp": datetime.now(tz=UTC).isoformat(
                                    timespec="seconds"
                                ),
                            },
                        },
                        "PaymentTransaction": {
                            "AmountsReq": {
                                "Currency": order.currency_id.name,
                                "RequestedAmount": order.amount_total,
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
