from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from odoo.tests import tagged

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment.tests.onboarding_common import OnboardingStateCases
from odoo.addons.payment_razorpay import const
from odoo.addons.payment_razorpay.controllers.onboarding import RazorpayController
from odoo.addons.payment_razorpay.tests.common import RazorpayCommon


@tagged("post_install", "-at_install")
class TestRazorpayOnboardingState(
    OnboardingStateCases, RazorpayCommon, PaymentHttpCommon
):
    return_route = RazorpayController.OAUTH_RETURN_URL

    def setUp(self):
        super().setUp()
        currency = self.provider.company_id.currency_id.name
        self.startPatcher(
            patch.object(
                const, "SUPPORTED_CURRENCIES", [*const.SUPPORTED_CURRENCIES, currency]
            )
        )
        self.startPatcher(
            patch.object(
                type(self.env["payment.provider"]), "action_razorpay_create_webhook"
            )
        )

    def _state_of_start_url(self, url) -> str:
        return parse_qs(urlsplit(url).query)["csrf_token"][0]

    def _return_query(self, state, provider_id) -> dict:
        return {
            "csrf_token": state,
            "provider_id": provider_id,
            "authorization_code": "an-authorization-code",
        }

    def _proxy_token_response(self) -> dict:
        return {
            "razorpay_account_id": "acc_onboarded",
            "public_token": "onboarded-public-token",
            "refresh_token": "onboarded-refresh-token",
            "access_token": "onboarded-access-token",
            "expires_in": 7776000,
        }

    def _is_onboarded(self, provider) -> bool:
        return (
            provider.state == "enabled"
            and provider.razorpay_access_token == "onboarded-access-token"
        )
