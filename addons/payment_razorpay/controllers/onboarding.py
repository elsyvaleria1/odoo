import pprint
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.http import Controller, request, route

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class RazorpayController(Controller):
    OAUTH_RETURN_URL = "/payment/razorpay/oauth/return"

    @route(OAUTH_RETURN_URL, type="http", auth="user", methods=["GET"], website=True)
    def razorpay_return_from_authorization(self, **data):
        """Exchange the authorization code for an access token and redirect to the provider form.

        :param dict data: The authorization code received from Razorpay, in addition to the
                          provider id and the state (as `csrf_token`, the field the proxy
                          echoes) the onboarding was started with, sent back by the proxy.
        :raise AccessError: If the state was not issued to this session, has expired or was
                            already used, names another provider than the echoed id, or if
                            the user may not configure its provider.
        :return: Redirect to the payment provider form.
        """
        _logger.info(
            "Returning from authorization with data:\n%s", pprint.pformat(data)
        )

        provider = request.env["payment.provider"]._consume_onboarding_state(
            "razorpay", data.get("csrf_token"), data.get("provider_id")
        )
        authorization_code = data.get("authorization_code")

        # Request and set the OAuth tokens on the provider.
        action = request.env.ref("payment.action_payment_provider")
        redirect_url = f"/odoo/action-{action.id}/{provider.id}"
        if not authorization_code:  # The user cancelled the authorization.
            return request.redirect(redirect_url)

        # Fetch an access token using the authorization token.
        proxy_payload = provider._prepare_json_rpc_payload(
            {"authorization_code": authorization_code}
        )
        try:
            response_content = provider._send_api_request(
                "POST", "/get_access_token", json=proxy_payload, is_proxy_request=True
            )
        except ValidationError as e:
            return request.render(
                "payment_razorpay.authorization_error",
                qcontext={"error_message": str(e), "provider_url": redirect_url},
            )
        expires_in = fields.Datetime.now() + timedelta(
            seconds=int(response_content["expires_in"])
        )
        provider.write(
            {
                # Reset the classical API key fields.
                "razorpay_key_id": None,
                "razorpay_key_secret": None,
                "razorpay_webhook_secret": None,
                # Save the OAuth credentials.
                "razorpay_account_id": response_content["razorpay_account_id"],
                "razorpay_public_token": response_content["public_token"],
                "razorpay_refresh_token": response_content["refresh_token"],
                "razorpay_access_token": response_content["access_token"],
                "razorpay_access_token_expiry": expires_in,
                # Enable the provider.
                "state": "enabled",
                "is_published": True,
            }
        )
        try:
            provider.action_razorpay_create_webhook()
        except ValidationError as error:
            _logger.warning(error)
        return request.redirect(redirect_url)
