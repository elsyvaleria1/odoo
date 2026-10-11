import pprint

from odoo import http, release
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import py_to_js_locale, urls

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_adyen import utils as adyen_utils

_logger = get_payment_logger(__name__)


class AdyenController(http.Controller):
    _webhook_url = "/payment/adyen/notification"

    @http.route("/payment/adyen/payment_methods", type="jsonrpc", auth="public")
    def adyen_payment_methods(
        self, provider_id, formatted_amount=None, partner_id=None
    ):
        provider_sudo = request.env["payment.provider"].sudo().browse(provider_id)
        partner_sudo = (
            partner_id and request.env["res.partner"].sudo().browse(partner_id).exists()
        )
        lang_code = py_to_js_locale(request.env.context.get("lang")) or "en-US"
        shopper_reference = partner_sudo and f"ODOO_PARTNER_{partner_sudo.id}"
        partner_country_code = (
            partner_sudo.country_id.code
            or provider_sudo.company_id.country_id.code
            or "NL"
        )
        data = {
            "merchantAccount": provider_sudo.adyen_merchant_account,
            "amount": formatted_amount,
            "countryCode": partner_country_code,
            "shopperLocale": lang_code,
            "shopperReference": shopper_reference,
            "channel": "Web",
        }
        response_content = provider_sudo._send_api_request(
            "POST", "/paymentMethods", json=data
        )
        response_content["country_code"] = partner_country_code
        return response_content

    @http.route("/payment/adyen/payments", type="jsonrpc", auth="public")
    def adyen_payments(
        self,
        provider_id,
        reference,
        converted_amount,
        currency_id,
        partner_id,
        payment_method,
        access_token,
        browser_info=None,
    ):
        if not payment_utils.is_access_token_valid(
            access_token, reference, converted_amount, currency_id, partner_id
        ):
            raise ValidationError(
                request.env._("Received tampered payment request data.")
            )

        provider_sudo = (
            request.env["payment.provider"].sudo().browse(provider_id).exists()
        )
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("provider_id", "=", provider_sudo.id),
                    ("reference", "=", reference),
                ]
            )
        )
        partner_country_code = (
            tx_sudo.partner_country_id.code
            or provider_sudo.company_id.country_id.code
            or "NL"
        )
        data = {
            "merchantAccount": provider_sudo.adyen_merchant_account,
            "amount": {
                "value": converted_amount,
                "currency": request.env["res.currency"]
                .browse(currency_id)
                .name,
            },
            "applicationInfo": {
                "externalPlatform": {
                    "name": "Odoo",
                    "version": release.version,
                    "integrator": "Odoo SA",
                }
            },
            "countryCode": partner_country_code,
            "reference": reference,
            "paymentMethod": payment_method,
            "shopperReference": provider_sudo._adyen_compute_shopper_reference(
                partner_id
            ),
            "recurringProcessingModel": "CardOnFile",
            "shopperIP": payment_utils.get_customer_ip_address(),
            "shopperInteraction": "Ecommerce",
            "shopperEmail": tx_sudo.partner_email or "",
            "shopperName": adyen_utils.format_partner_name(tx_sudo.partner_name),
            "telephoneNumber": tx_sudo.partner_phone or "",
            "storePaymentMethod": tx_sudo.tokenize,
            "authenticationData": {
                "threeDSRequestData": {
                    "nativeThreeDS": "preferred",
                }
            },
            "channel": "web",
            "origin": provider_sudo.get_base_url(),
            "browserInfo": browser_info,
            "returnUrl": urls.urljoin(
                provider_sudo.get_base_url(),
                f"/payment/adyen/return?merchantReference={reference}",
            ),
            **adyen_utils.include_partner_addresses(tx_sudo),
            "lineItems": [
                {
                    "amountIncludingTax": converted_amount,
                    "quantity": "1",
                    "description": reference,
                }
            ],
        }

        if not provider_sudo.capture_manually:
            data.update(captureDelayHours=0)

        idempotency_key = payment_utils.generate_idempotency_key(
            tx_sudo, scope="payment_request_controller"
        )

        response_content = provider_sudo._send_api_request(
            "POST", "/payments", json=data, idempotency_key=idempotency_key
        )
        tx_sudo._process(
            "adyen",
            dict(
                response_content, merchantReference=reference
            ),
        )
        return response_content

    @http.route("/payment/adyen/payments/details", type="jsonrpc", auth="public")
    def adyen_payment_details(self, provider_id, reference, payment_details):
        provider_sudo = request.env["payment.provider"].browse(provider_id).sudo()
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("provider_id", "=", provider_sudo.id),
                    ("reference", "=", reference),
                ]
            )
        )

        idempotency_key = payment_utils.generate_idempotency_key(
            tx_sudo, scope="payment_details_request_controller"
        )

        response_content = provider_sudo._send_api_request(
            "POST",
            "/payments/details",
            json=payment_details,
            idempotency_key=idempotency_key,
        )

        request.env["payment.transaction"].sudo()._process(
            "adyen",
            dict(
                response_content, merchantReference=reference
            ),
        )

        return response_content

    @http.route(
        "/payment/adyen/return",
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_adyen_return",
        csrf=False,
        save_session=False,
        typed=True,
    )
    def adyen_return_from_3ds_auth(self, **data):
        tx_sudo = request.admission.subject

        tx_sudo.operation = "online_redirect"

        _logger.info(
            "Handling redirection from Adyen for transaction %s with data:\n%s",
            tx_sudo.reference,
            pprint.pformat(data),
        )
        self.adyen_payment_details(
            tx_sudo.provider_id.id,
            data["merchantReference"],
            {
                "details": {
                    "redirectResult": data["redirectResult"],
                },
            },
        )

        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="payment.provider:_receiver_for_adyen_webhook",
        csrf=False,
        typed=True,
    )
    def adyen_webhook(self):
        for payment_data in request.admission.extra["items"]:
            _logger.info(
                "notification received from Adyen with data:\n%s",
                pprint.pformat(payment_data),
            )
            success = payment_data["success"] == "true"
            event_code = payment_data["eventCode"]
            if event_code == "AUTHORISATION" and success:
                payment_data["resultCode"] = "Authorised"
            elif event_code == "CANCELLATION":
                payment_data["resultCode"] = "Cancelled" if success else "Error"
            elif event_code in ["REFUND", "CAPTURE"]:
                payment_data["resultCode"] = "Authorised" if success else "Error"
            elif event_code == "CAPTURE_FAILED" and success:
                payment_data["resultCode"] = "Error"
            else:
                continue
            tx_sudo = request.admission.subject.env[
                "payment.transaction"
            ]._search_by_reference("adyen", payment_data)
            if tx_sudo:
                tx_sudo._process("adyen", payment_data)
        return request.prepare_json_response(
            "[accepted]"
        )
