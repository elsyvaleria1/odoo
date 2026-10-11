from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from freezegun import freeze_time

from odoo.tests import JsonRpcException, tagged
from odoo.tools import mute_logger

from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.addons.payment.tests.http_common import PaymentHttpCommon


@tagged("post_install", "-at_install")
class TestFlows(PaymentHttpCommon):
    def _test_flow(self, flow):
        self.reference = f"Test Transaction ({flow} - {self.partner.name})"
        route_values = self._prepare_pay_values()

        payment_context = self._get_portal_pay_context(**route_values)
        for key, val in payment_context.items():
            if key in route_values:
                self.assertEqual(val, route_values[key])

        route_values = {
            k: payment_context[k]
            for k in [
                "amount",
                "currency_id",
                "partner_id",
                "landing_route",
                "reference_prefix",
                "access_token",
            ]
        }
        route_values.update(
            {
                "provider_id": self.provider.id,
                "payment_method_id": self.payment_method_id
                if flow != "token"
                else None,
                "token_id": self._create_token().id if flow == "token" else None,
                "flow": flow,
                "tokenization_requested": False,
            }
        )

        with mute_logger("odoo.addons.payment.models.payment_transaction"):
            processing_values = self._get_processing_values(**route_values)
        tx_sudo = self._get_tx(processing_values["reference"])

        self.assertEqual(tx_sudo.provider_id.id, self.provider.id)
        self.assertEqual(tx_sudo.amount, self.amount)
        self.assertEqual(tx_sudo.currency_id.id, self.currency.id)
        self.assertEqual(tx_sudo.partner_id.id, self.partner.id)
        self.assertEqual(tx_sudo.reference, self.reference)

        self.assertEqual(processing_values["provider_id"], self.provider.id)
        self.assertEqual(processing_values["amount"], self.amount)
        self.assertEqual(processing_values["currency_id"], self.currency.id)
        self.assertEqual(processing_values["partner_id"], self.partner.id)
        self.assertEqual(processing_values["reference"], self.reference)
        self.assertFalse(processing_values["should_tokenize"])

        self.assertIn("tx_id=", tx_sudo.landing_route)
        self.assertIn("access_token=", tx_sudo.landing_route)

        if flow == "redirect":
            redirect_form_info = self._extract_values_from_html_form(
                processing_values["redirect_form_html"]
            )

            self.assertEqual(redirect_form_info["action"], "dummy")
            self.assertEqual(redirect_form_info["inputs"]["user_id"], str(self.user.id))
            self.assertEqual(
                redirect_form_info["inputs"]["view_id"],
                str(self.dummy_provider.redirect_form_view_id.id),
            )

        return tx_sudo

    def test_10_direct_checkout_public(self):
        self.user = self.public_user
        self.partner.company_id = self.env.company.id
        self._test_flow("direct")

    def test_11_direct_checkout_portal(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.user = self.portal_user
        self.partner = self.portal_partner
        self._test_flow("direct")

    def test_12_direct_checkout_internal(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        self.user = self.internal_user
        self.partner = self.internal_partner
        self._test_flow("direct")

    def test_20_redirect_checkout_public(self):
        self.user = self.public_user
        self.partner.company_id = self.env.company.id
        self._test_flow("redirect")

    def test_21_redirect_checkout_portal(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.user = self.portal_user
        self.partner = self.portal_partner
        self._test_flow("redirect")

    def test_22_redirect_checkout_internal(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        self.user = self.internal_user
        self.partner = self.internal_partner
        self._test_flow("redirect")



    def test_31_tokenize_portal(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self.user = self.portal_user
        self._test_flow("token")

    def test_32_tokenize_internal(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        self.partner = self.internal_partner
        self.user = self.internal_user
        self._test_flow("token")



    @freeze_time("2011-11-02 12:00:21")
    def _test_validation(self, flow):
        expected_reference = "V-20111102120021"

        validation_amount = self.provider._get_validation_amount()
        validation_currency = self.provider._get_validation_currency()

        payment_context = self._get_portal_payment_method_context()
        expected_values = {
            "partner_id": self.partner.id,
            "access_token": self._generate_test_access_token(
                self.partner.id, None, None
            ),
            "reference_prefix": expected_reference,
        }
        for key, val in payment_context.items():
            if key in expected_values:
                self.assertEqual(val, expected_values[key])

        transaction_values = {
            "provider_id": self.provider.id,
            "payment_method_id": self.payment_method_id,
            "token_id": None,
            "amount": None,
            "currency_id": None,
            "partner_id": payment_context["partner_id"],
            "access_token": payment_context["access_token"],
            "flow": flow,
            "tokenization_requested": True,
            "landing_route": payment_context["landing_route"],
            "reference_prefix": payment_context["reference_prefix"],
            "is_validation": True,
        }
        with mute_logger("odoo.addons.payment.models.payment_transaction"):
            processing_values = self._get_processing_values(**transaction_values)
        tx_sudo = self._get_tx(processing_values["reference"])

        self.assertEqual(tx_sudo.provider_id.id, self.provider.id)
        self.assertEqual(tx_sudo.amount, validation_amount)
        self.assertEqual(tx_sudo.currency_id.id, validation_currency.id)
        self.assertEqual(tx_sudo.partner_id.id, self.partner.id)
        self.assertEqual(tx_sudo.reference, expected_reference)
        self.assertEqual(processing_values["amount"], validation_amount)
        self.assertEqual(processing_values["currency_id"], validation_currency.id)
        self.assertEqual(processing_values["partner_id"], self.partner.id)
        self.assertEqual(processing_values["reference"], expected_reference)

    def test_51_validation_direct_portal(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self._test_validation(flow="direct")

    def test_52_validation_direct_internal(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        self.partner = self.internal_partner
        self._test_validation(flow="direct")

    def test_61_validation_redirect_portal(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self._test_validation(flow="direct")

    def test_62_validation_redirect_internal(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        self.partner = self.internal_partner
        self._test_validation(flow="direct")


    def test_pay_redirect_if_no_partner_exist(self):
        route_values = self._prepare_pay_values()
        route_values.pop("partner_id")

        response = self._portal_pay(**route_values)
        url = urlparse(response.url)
        self.assertEqual(url.path, "/web/login")
        self.assertIn("redirect", parse_qs(url.query))

        self.authenticate(self.portal_user.login, self.portal_user.login)
        tx_context = self._get_portal_pay_context(**route_values)
        self.assertEqual(tx_context["partner_id"], self.portal_partner.id)

    def test_pay_no_token(self):
        route_values = self._prepare_pay_values()
        route_values.pop("partner_id")
        route_values.pop("access_token")

        response = self._portal_pay(**route_values)
        url = urlparse(response.url)
        self.assertEqual(url.path, "/web/login")
        self.assertIn("redirect", parse_qs(url.query))

        self.authenticate(self.portal_user.login, self.portal_user.login)
        tx_context = self._get_portal_pay_context(**route_values)
        self.assertEqual(tx_context["partner_id"], self.portal_partner.id)

    def test_pay_wrong_token(self):
        route_values = self._prepare_pay_values()
        route_values["access_token"] = "abcde"

        response = self._portal_pay(**route_values)
        self.assertEqual(response.status_code, 404)

    def test_pay_wrong_currency(self):
        self.currency = self.env["res.currency"].browse(
            self.env["res.currency"].search([], order="id desc", limit=1).id + 1000
        )
        route_values = self._prepare_pay_values()
        response = self._portal_pay(**route_values)
        self.assertEqual(response.status_code, 404)

        self.currency = self.env["res.currency"].search(
            [("active", "=", False)], limit=1
        )
        route_values = self._prepare_pay_values()
        response = self._portal_pay(**route_values)
        self.assertEqual(response.status_code, 404)

    def test_transaction_wrong_flow(self):
        transaction_values = self._prepare_pay_values()
        transaction_values.pop("reference")
        transaction_values.update(
            {
                "flow": "this flow does not exist",
                "payment_option_id": self.provider.id,
                "tokenization_requested": False,
                "landing_route": "whatever",
                "reference_prefix": "whatever",
            }
        )
        with (
            mute_logger("odoo.http"),
            self.assertRaises(
                JsonRpcException,
                msg="odoo.exceptions.UserError: The payment should either be direct, with redirection, or made by a token.",
            ),
        ):
            self._portal_transaction(**transaction_values)

    @mute_logger("odoo.http")
    def test_transaction_route_rejects_unexpected_kwarg(self):
        route_kwargs = {
            **self._prepare_pay_values(),
            "custom_create_values": "whatever",
        }
        with self.assertRaises(JsonRpcException, msg="odoo.exceptions.ValidationError"):
            self._portal_transaction(**route_kwargs)

    def test_transaction_wrong_token(self):
        route_values = self._prepare_pay_values()
        route_values["access_token"] = "abcde"

        with (
            mute_logger("odoo.http"),
            self.assertRaises(
                JsonRpcException,
                msg="odoo.exceptions.ValidationError: The access token is invalid.",
            ),
        ):
            self._portal_transaction(**route_values)

    def test_access_disabled_providers_tokens(self):
        self.partner = self.portal_partner

        self.authenticate(self.portal_user.login, self.portal_user.login)

        token = self._create_token()
        provider_b = self.provider.copy({"is_published": True, "state": "test"})
        token_b = self._create_token(provider_id=provider_b.id)

        payment_context = self._get_portal_payment_method_context()
        self.assertEqual(payment_context["partner_id"], self.partner.id)
        self.assertIn(token.id, payment_context["token_ids"])
        self.assertIn(token_b.id, payment_context["token_ids"])
        self.assertIn(self.payment_method_id, payment_context["payment_method_ids"])

        self.provider.state = "disabled"
        payment_context = self._get_portal_payment_method_context()
        self.assertEqual(payment_context["partner_id"], self.partner.id)
        self.assertEqual(payment_context["token_ids"], [token_b.id])

        token_b.active = False
        payment_context = self._get_portal_payment_method_context()
        self.assertEqual(payment_context["partner_id"], self.partner.id)
        self.assertEqual(payment_context["token_ids"], [])

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_direct_payment_triggers_no_payment_request(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self.user = self.portal_user
        with patch(
            "odoo.addons.payment.models.payment_transaction.PaymentTransaction"
            "._charge_with_token"
        ) as patched:
            self._portal_transaction(
                **self._prepare_transaction_values(
                    self.payment_method_id, None, "direct"
                )
            )
            self.assertEqual(patched.call_count, 0)

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_payment_with_redirect_triggers_no_payment_request(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self.user = self.portal_user
        with patch(
            "odoo.addons.payment.models.payment_transaction.PaymentTransaction"
            "._charge_with_token"
        ) as patched:
            self._portal_transaction(
                **self._prepare_transaction_values(
                    self.payment_method_id, None, "redirect"
                )
            )
            self.assertEqual(patched.call_count, 0)

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_payment_by_token_triggers_exactly_one_payment_request(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.partner = self.portal_partner
        self.user = self.portal_user
        with patch(
            "odoo.addons.payment.models.payment_transaction.PaymentTransaction"
            "._charge_with_token"
        ) as patched:
            self._portal_transaction(
                **self._prepare_transaction_values(
                    None, self._create_token().id, "token"
                )
            )
            self.assertEqual(patched.call_count, 1)

    def test_tokenization_input_is_shown_to_logged_in_users(self):
        self.user = self.portal_user
        self.provider.allow_tokenization = True

        show_tokenize_input = PaymentPortal._get_show_tokenize_input_mapping(
            self.provider
        )
        self.assertDictEqual(show_tokenize_input, {self.provider.id: True})

        self.user = self.internal_user
        self.provider.allow_tokenization = True

        show_tokenize_input = PaymentPortal._get_show_tokenize_input_mapping(
            self.provider
        )
        self.assertDictEqual(show_tokenize_input, {self.provider.id: True})

    def test_tokenization_input_is_shown_to_logged_out_users(self):
        self.user = self.public_user
        self.provider.allow_tokenization = True

        show_tokenize_input = PaymentPortal._get_show_tokenize_input_mapping(
            self.provider
        )
        self.assertDictEqual(show_tokenize_input, {self.provider.id: True})
