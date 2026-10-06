import pprint
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.http import Controller, request, route

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_mercado_pago import const

_logger = get_payment_logger(__name__)


class MercadoPagoOnboardingController(Controller):
    @route(
        const.OAUTH_RETURN_ROUTE,
        type="http",
        auth="user",
        methods=["GET"],
        website=True,
    )
    def mercado_pago_return_from_authorization(self, **data):
        """Exchange the authorization code for an access token and redirect to the provider form.

        :param dict data: The authorization code received from Mercado Pago, in addition to the
                          state the onboarding was started with, sent back by the proxy.
        :raise AccessError: If the state was not issued to this session, has expired or was
                            already used, or if the user may not configure its provider.
        :return: Redirect to the payment provider form.
        """
        _logger.info(
            "Returning from authorization with data:\n%s", pprint.pformat(data)
        )

        provider = request.env["payment.provider"]._consume_onboarding_state(
            "mercado_pago", data.get("state"), data.get("provider_id")
        )
        authorization_code = data.get(
            "authorization_code"
        )  # Could be missing if authorization was cancelled.

        # Request and set the OAuth tokens on the provider.
        action = request.env.ref("payment.action_payment_provider")
        redirect_url = f"/odoo/action-{action.id}/{provider.id}"
        if not authorization_code:  # The user cancelled the authorization.
            return request.redirect(redirect_url)

        # Fetch an access token using the authorization token.
        proxy_payload = provider._prepare_json_rpc_payload(
            {
                "authorization_code": authorization_code,
                "account_country_code": provider.mercado_pago_account_country_id.code.lower(),
            }
        )
        try:
            response_content = provider._send_api_request(
                "POST",
                "/get_access_token",
                json=proxy_payload,
                is_proxy_request=True,
            )
        except ValidationError as e:
            return request.render(
                "payment_mercado_pago.authorization_error",
                {"error_message": str(e), "provider_url": redirect_url},
            )
        # Backdate the access token expiry to refresh it before it expires, since the refresh token
        # would become unusable at that time (according to Mercado Pago's dev team).
        expires_in = (
            fields.Datetime.now()
            + timedelta(seconds=int(response_content["expires_in"]))
            - timedelta(days=31)
        )
        provider.write(
            {
                # Save the OAuth credentials.
                "mercado_pago_access_token": response_content["access_token"],
                "mercado_pago_refresh_token": response_content["refresh_token"],
                "mercado_pago_access_token_expiry": expires_in,
                "mercado_pago_public_key": response_content["public_key"],
                # Enable the provider.
                "state": "enabled",
                "is_published": True,
                "allow_tokenization": True,
            }
        )

        return request.redirect(redirect_url)
