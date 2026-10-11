from odoo import http
from odoo.http import request


class OnboardingController(http.Controller):
    _onboarding_return_url = "/payment/stripe/onboarding/return"
    _onboarding_refresh_url = "/payment/stripe/onboarding/refresh"

    @http.route(_onboarding_return_url, type="http", methods=["GET"], auth="user")
    def stripe_return_from_onboarding(self, provider_id, menu_id):
        url = f"/odoo/action-payment_stripe.action_payment_provider_onboarding/{provider_id}?menu_id={menu_id}"
        return request.redirect(url)

    @http.route(_onboarding_refresh_url, type="http", methods=["GET"], auth="user")
    def stripe_refresh_onboarding(self, provider_id, account_id, menu_id):
        stripe_provider = request.env["payment.provider"].browse(int(provider_id))
        account_link = stripe_provider._stripe_create_account_link(
            account_id, int(menu_id)
        )
        return request.redirect(account_link, local=False)
