import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import file_open

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_stripe import const

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class StripeController(http.Controller):
    _return_url = "/payment/stripe/return"
    _webhook_url = "/payment/stripe/webhook"
    _apple_pay_domain_association_url = (
        "/.well-known/apple-developer-merchantid-domain-association"
    )

    @http.route(_return_url, type="http", methods=["GET"], auth="public")
    def stripe_return(self, **data):
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._search_by_reference("stripe", data)
        )
        endpoint = (
            f"payment_intents/{data.get('payment_intent')}"
            if tx_sudo.operation != "validation"
            else f"setup_intents/{data.get('setup_intent')}"
        )
        try:
            response_content = tx_sudo._send_api_request(
                "GET",
                endpoint,
                data={"expand[]": "payment_method"},
            )
        except ValidationError:
            _logger.error("Failed to process the return from Stripe.")
        else:
            if tx_sudo.operation != "validation":
                self._include_payment_intent_in_payment_data(response_content, data)
            else:
                self._include_setup_intent_in_payment_data(response_content, data)
            tx_sudo._process("stripe", data)

        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="payment.transaction:_receiver_for_stripe_notification",
        receiver_refusal="payment.transaction:_refuse_stripe_notification",
        csrf=False,
        typed=True,
    )
    def stripe_webhook(self):
        admission = request.admission
        tx_sudo = admission.subject
        event = admission.extra["event"]
        stripe_object = admission.extra["stripe_object"]
        data = admission.extra["data"]
        _logger.info(
            "Notification received from Stripe with data:\n%s", pprint.pformat(event)
        )
        try:
            if event["type"].startswith("payment_intent"):
                if tx_sudo.tokenize:
                    payment_method = tx_sudo._send_api_request(
                        "GET", f"payment_methods/{stripe_object['payment_method']}"
                    )
                    stripe_object["payment_method"] = payment_method
                self._include_payment_intent_in_payment_data(stripe_object, data)
            elif event["type"].startswith("setup_intent"):
                payment_method = tx_sudo._send_api_request(
                    "GET", f"payment_methods/{stripe_object['payment_method']}"
                )
                stripe_object["payment_method"] = payment_method
                self._include_setup_intent_in_payment_data(stripe_object, data)
            elif event["type"] == "charge.refunded":
                refunds = stripe_object["refunds"]["data"]

                has_more = stripe_object["refunds"]["has_more"]
                while has_more:
                    payload = {
                        "charge": stripe_object["id"],
                        "starting_after": refunds[-1]["id"],
                        "limit": 100,
                    }
                    additional_refunds = tx_sudo._send_api_request(
                        "GET", "refunds", data=payload
                    )
                    refunds += additional_refunds["data"]
                    has_more = additional_refunds["has_more"]

                processed_refund_ids = tx_sudo.child_transaction_ids.filtered(
                    lambda tx: tx.operation == "refund"
                ).mapped("provider_reference")
                for refund in filter(
                    lambda r: r["id"] not in processed_refund_ids, refunds
                ):
                    refund_tx_sudo = self._create_refund_tx_from_refund(tx_sudo, refund)
                    self._include_refund_in_payment_data(refund, data)
                    refund_tx_sudo._process("stripe", data)
                return request.prepare_json_response("")
            elif event["type"] == "charge.refund.updated":
                self._include_refund_in_payment_data(stripe_object, data)

            tx_sudo._process("stripe", data)
        except ValidationError:
            _logger.exception(
                "Unable to process the payment data; skipping to acknowledge"
            )
        return request.prepare_json_response("")

    @staticmethod
    def _include_payment_intent_in_payment_data(payment_intent, payment_data):
        payment_data.update(
            {
                "payment_intent": payment_intent,
                "payment_method": payment_intent.get("payment_method"),
            }
        )

    @staticmethod
    def _include_setup_intent_in_payment_data(setup_intent, payment_data):
        payment_data.update(
            {
                "setup_intent": setup_intent,
                "payment_method": setup_intent.get("payment_method"),
            }
        )

    @staticmethod
    def _include_refund_in_payment_data(refund, payment_data):
        payment_data.update(refund=refund)

    @staticmethod
    def _create_refund_tx_from_refund(source_tx_sudo, refund_object):
        amount_to_refund = refund_object["amount"]
        converted_amount = payment_utils.minor_to_major_currency_units(
            amount_to_refund,
            source_tx_sudo.currency_id,
            arbitrary_decimal_number=const.CURRENCY_DECIMALS.get(
                source_tx_sudo.currency_id.name
            ),
        )
        return source_tx_sudo._create_child_transaction(
            converted_amount, is_refund=True
        )

    @http.route(
        _apple_pay_domain_association_url, type="http", methods=["GET"], auth="public"
    )
    def stripe_apple_pay_get_domain_association_file(self):
        with file_open(
            "payment_stripe/static/files/apple-developer-merchantid-domain-association"
        ) as f:
            return f.read()
