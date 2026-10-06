from urllib.parse import parse_qs, urlsplit

from odoo.tests import tagged

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment.tests.onboarding_common import OnboardingStateCases
from odoo.addons.payment_mercado_pago import const
from odoo.addons.payment_mercado_pago.tests.common import MercadoPagoCommon


@tagged("post_install", "-at_install")
class TestMercadoPagoOnboardingState(
    OnboardingStateCases, MercadoPagoCommon, PaymentHttpCommon
):
    return_route = const.OAUTH_RETURN_ROUTE

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider.company_id.country_id = cls.env.ref("base.mx")

    def _state_of_start_url(self, url) -> str:
        return_url = parse_qs(urlsplit(url).query)["return_url"][0]
        return parse_qs(urlsplit(return_url).query)["state"][0]

    def _return_query(self, state, provider_id) -> dict:
        return {
            "state": state,
            "provider_id": provider_id,
            "authorization_code": "an-authorization-code",
        }

    def _proxy_token_response(self) -> dict:
        return {
            "access_token": "onboarded-access-token",
            "refresh_token": "onboarded-refresh-token",
            "expires_in": 15552000,
            "public_key": "onboarded-public-key",
        }

    def _is_onboarded(self, provider) -> bool:
        return (
            provider.state == "enabled"
            and provider.mercado_pago_access_token == "onboarded-access-token"
        )
