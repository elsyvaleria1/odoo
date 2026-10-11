from json.decoder import JSONDecodeError
from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.libs.guarded_http import GuardedSession
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment.tests.common import PaymentCommon


@tagged("-at_install", "post_install")
class TestPaymentProvider(PaymentCommon):
    def test_changing_provider_state_archives_tokens(self):
        for old_state in (
            "enabled",
            "test",
        ):
            for new_state in ("enabled", "test", "disabled"):
                if (
                    old_state != new_state
                ):
                    self.provider.state = old_state
                    token = self._create_token()
                    self.provider.state = new_state
                    self.assertFalse(token.active)

    def test_enabling_provider_activates_default_payment_methods(self):
        self.payment_methods.active = False
        for new_state in ("enabled", "test"):
            self.provider.state = "disabled"
            with patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider"
                "._get_default_payment_method_codes",
                return_value={self.payment_method_code},
            ):
                self.provider.state = new_state
                self.assertTrue(self.payment_methods.active)

    def test_enabling_manual_capture_provider_activates_compatible_default_pms(self):
        payment_method_with_manual_capture = self.env["payment.method"].create(
            {
                "image": self.payment_method.image,
                "name": "Payment Method With Manual Capture",
                "code": "pm_with_manual_capture",
                "support_manual_capture": "full_only",
            }
        )
        self.provider.state = "disabled"
        self.provider.capture_manually = True
        self.provider.payment_method_ids = [
            Command.set([self.payment_method.id, payment_method_with_manual_capture.id])
        ]
        self.payment_method.support_manual_capture = "none"
        default_codes = {
            self.payment_method_code,
            payment_method_with_manual_capture.code,
        }
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider"
            "._get_default_payment_method_codes",
            return_value=default_codes,
        ):
            self.provider.state = "test"
            self.assertFalse(self.payment_methods.active)
            self.assertTrue(payment_method_with_manual_capture.active)

    def test_disabling_provider_deactivates_default_payment_methods(self):
        self.payment_methods.active = True
        for old_state in ("enabled", "test"):
            self.provider.state = old_state
            with patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider"
                "._get_default_payment_method_codes",
                return_value=self.payment_method_code,
            ):
                self.provider.state = "disabled"
                self.assertFalse(self.payment_methods.active)

    def test_enabling_provider_activates_processing_cron(self):
        self.env["payment.provider"].search(
            []
        ).state = "disabled"
        post_processing_cron = self.env.ref("payment.cron_post_process_payment_tx")
        for enabled_state in ("enabled", "test"):
            post_processing_cron.active = False
            self.provider.state = "disabled"
            self.provider.state = enabled_state
            self.assertTrue(post_processing_cron.active)

    def test_disabling_provider_deactivates_processing_cron(self):
        self.env["payment.provider"].search(
            []
        ).state = "disabled"
        post_processing_cron = self.env.ref("payment.cron_post_process_payment_tx")
        for enabled_state in ("enabled", "test"):
            post_processing_cron.active = True
            self.provider.state = (
                enabled_state
            )
            self.provider.state = "disabled"
            self.assertFalse(post_processing_cron.active)

    def test_published_provider_compatible_with_all_users(self):
        for user in (self.public_user, self.portal_user):
            self.env = self.env(user=user)

            compatible_providers = (
                self.env["payment.provider"]
                .sudo()
                ._get_compatible_providers(
                    self.company.id, self.partner.id, self.amount
                )
            )
            self.assertIn(self.provider, compatible_providers)

    def test_unpublished_provider_compatible_with_internal_user(self):
        self.provider.is_published = False

        compatible_providers = self.env["payment.provider"]._get_compatible_providers(
            self.company.id, self.partner.id, self.amount
        )
        self.assertIn(self.provider, compatible_providers)

    def test_unpublished_provider_not_compatible_with_non_internal_user(self):
        self.provider.is_published = False
        for user in (self.public_user, self.portal_user):
            self.env = self.env(user=user)

            compatible_providers = (
                self.env["payment.provider"]
                .sudo()
                ._get_compatible_providers(
                    self.company.id, self.partner.id, self.amount
                )
            )
            self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_with_branch_companies(self):
        branch_company = self.env["res.company"].create(
            {
                "name": "Provider Branch Company",
                "parent_id": self.provider.company_id.id,
            }
        )
        compatible_providers = self.provider._get_compatible_providers(
            branch_company.id,
            self.partner.id,
            self.amount,
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_compatible_with_available_countries(self):
        belgium = self.env.ref("base.be")
        self.provider.available_country_ids = [Command.set([belgium.id])]
        self.partner.country_id = belgium
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_with_unavailable_countries(self):
        belgium = self.env.ref("base.be")
        self.provider.available_country_ids = [Command.set([belgium.id])]
        france = self.env.ref("base.fr")
        self.partner.country_id = france
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount
        )
        self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_when_no_available_countries_set(self):
        self.provider.available_country_ids = [Command.clear()]
        belgium = self.env.ref("base.be")
        self.partner.country_id = belgium
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_compatible_when_maximum_amount_is_zero(self):
        self.provider.maximum_amount = 0.0
        currency = self.provider.main_currency_id.id

        compatible_providers = self.env["payment.provider"]._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, currency_id=currency
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_compatible_when_payment_below_maximum_amount(self):
        self.provider.maximum_amount = self.amount + 10.0
        currency = self.provider.main_currency_id.id

        compatible_providers = self.env["payment.provider"]._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, currency_id=currency
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_when_payment_above_maximum_amount(self):
        self.provider.maximum_amount = self.amount - 10.0
        currency = self.provider.main_currency_id.id

        compatible_providers = self.env["payment.provider"]._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, currency_id=currency
        )
        self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_with_available_currencies(self):
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id,
            self.partner.id,
            self.amount,
            currency_id=self.currency_euro.id,
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_with_unavailable_currencies(self):
        self.provider.available_currency_ids = [Command.unlink(self.currency_usd.id)]
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id,
            self.partner.id,
            self.amount,
            currency_id=self.currency_usd.id,
        )
        self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_when_no_available_currencies_set(self):
        self.provider.available_currency_ids = [Command.clear()]
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id,
            self.partner.id,
            self.amount,
            currency_id=self.currency_euro.id,
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_compatible_when_tokenization_forced(self):
        self.provider.allow_tokenization = True
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, force_tokenization=True
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_when_tokenization_forced(self):
        self.provider.allow_tokenization = False
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, force_tokenization=True
        )
        self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_when_tokenization_required(self):
        self.provider.allow_tokenization = True
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._is_tokenization_required",
            return_value=True,
        ):
            compatible_providers = self.provider._get_compatible_providers(
                self.company.id, self.partner.id, self.amount
            )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_when_tokenization_required(self):
        self.provider.allow_tokenization = False
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._is_tokenization_required",
            return_value=True,
        ):
            compatible_providers = self.provider._get_compatible_providers(
                self.company.id, self.partner.id, self.amount
            )
        self.assertNotIn(self.provider, compatible_providers)

    def test_provider_compatible_with_express_checkout(self):
        self.provider.allow_express_checkout = True
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, is_express_checkout=True
        )
        self.assertIn(self.provider, compatible_providers)

    def test_provider_not_compatible_with_express_checkout(self):
        self.provider.allow_express_checkout = False
        compatible_providers = self.provider._get_compatible_providers(
            self.company.id, self.partner.id, self.amount, is_express_checkout=True
        )
        self.assertNotIn(self.provider, compatible_providers)

    def test_availability_report_covers_all_reasons(self):
        providers = self.env["payment.provider"].search([])
        providers.state = "disabled"

        self.provider.write(
            {
                "state": "test",
                "allow_express_checkout": True,
                "allow_tokenization": True,
            }
        )

        invalid_country_provider = self.provider.copy()
        belgium = self.env.ref("base.be")
        invalid_country_provider.write(
            {
                "state": "test",
                "available_country_ids": [Command.set([belgium.id])],
            }
        )
        france = self.env.ref("base.fr")
        self.partner.country_id = france

        exceeding_max_provider = self.provider.copy()
        exceeding_max_provider.write(
            {
                "state": "test",
                "maximum_amount": self.amount - 10.0,
            }
        )

        invalid_currency_provider = self.provider.copy()
        invalid_currency_provider.write(
            {
                "state": "test",
                "available_currency_ids": [Command.unlink(self.currency_usd.id)],
            }
        )

        no_tokenization_provider = self.provider.copy()
        no_tokenization_provider.write(
            {
                "state": "test",
                "allow_tokenization": False,
            }
        )

        no_express_checkout_provider = self.provider.copy()
        no_express_checkout_provider.write(
            {
                "state": "test",
                "allow_express_checkout": False,
            }
        )

        report = {}
        self.env["payment.provider"]._get_compatible_providers(
            self.company_id,
            self.partner.id,
            self.amount,
            currency_id=self.currency_usd.id,
            force_tokenization=True,
            is_express_checkout=True,
            report=report,
        )

        expected_providers_report = {
            self.provider: {
                "available": True,
                "reason": "",
            },
            invalid_country_provider: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["incompatible_country"],
            },
            exceeding_max_provider: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["exceed_max_amount"],
            },
            invalid_currency_provider: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["incompatible_currency"],
            },
            no_tokenization_provider: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["tokenization_not_supported"],
            },
            no_express_checkout_provider: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["express_checkout_not_supported"],
            },
        }
        self.maxDiff = None
        self.assertDictEqual(report["providers"], expected_providers_report)

    def test_validation_currency_is_supported(self):
        self.provider.available_currency_ids = [
            Command.clear()
        ]
        self.payment_method.supported_currency_ids = [
            Command.clear()
        ]
        validation_currency = self.provider.with_context(
            validation_pm=self.payment_method
        )._get_validation_currency()
        self.assertEqual(validation_currency, self.provider.company_id.currency_id)

        self.provider.available_currency_ids = [Command.set(self.currency_usd.ids)]
        self.payment_method.supported_currency_ids = [
            Command.clear()
        ]
        validation_currency = self.provider.with_context(
            validation_pm=self.payment_method
        )._get_validation_currency()
        self.assertIn(validation_currency, self.provider.available_currency_ids)

        self.provider.available_currency_ids = [
            Command.clear()
        ]
        self.payment_method.supported_currency_ids = [
            Command.set(self.currency_usd.ids)
        ]
        validation_currency = self.provider.with_context(
            validation_pm=self.payment_method
        )._get_validation_currency()
        self.assertIn(validation_currency, self.payment_method.supported_currency_ids)

        self.provider.available_currency_ids = [Command.set(self.currency_usd.ids)]
        self.payment_method.supported_currency_ids = [
            Command.set(self.currency_usd.ids)
        ]
        validation_currency = self.provider.with_context(
            validation_pm=self.payment_method
        )._get_validation_currency()
        self.assertIn(validation_currency, self.provider.available_currency_ids)
        self.assertIn(validation_currency, self.payment_method.supported_currency_ids)

    @mute_logger("odoo.addons.payment.models.payment_provider")
    def _ok_response(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        return response

    def test_a_provider_request_goes_through_the_provider_connection(self):
        with patch.object(GuardedSession, "request", return_value=self._ok_response()):
            self.provider._send_api_request("GET", "/dummy")
        self.env.flush_all()
        self.env.cr.precommit.run()

        connection = self.provider._get_integration_connection()
        row = self.env["integration.exchange"].search(
            [("connection_id", "=", connection.id)], limit=1
        )
        self.assertEqual(row.tags, "egress:payment_none")
        self.assertEqual(connection.service_id.code, "payment_none")
        self.assertEqual(connection.service_id.category, "payment")

    def test_a_paused_provider_says_so_instead_of_calling(self):
        connection = self.provider._get_integration_connection()
        connection.write({"breaker_failure_threshold": 1, "breaker_max_cooldown": 60})
        with patch("odoo.libs.breaker.monotonic", return_value=1000.0):
            with (
                patch.object(
                    GuardedSession,
                    "request",
                    side_effect=requests.ConnectionError("down"),
                ),
                self.assertRaises(ValidationError),
            ):
                self.provider._send_api_request("GET", "/dummy")

            with (
                patch.object(GuardedSession, "request") as sent,
                self.assertRaisesRegex(ValidationError, "paused"),
            ):
                self.provider._send_api_request("GET", "/dummy")
        sent.assert_not_called()

    def test_deleting_a_provider_deletes_its_connection(self):
        provider = self.provider.copy()
        connection = provider._get_integration_connection()

        provider.unlink()

        self.assertFalse(connection.exists())

    @mute_logger("odoo.addons.payment.models.payment_provider")
    def test_parsing_non_json_response_falls_back_to_text_response(self):
        response = requests.Response()
        response.status_code = 502
        response._content = b"<html><body>Cloudflare Error</body></html>"
        with (
            patch.object(GuardedSession, "request", return_value=response),
            patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._parse_response_error",
                new=lambda _self, _response: _response.json(),
            ),
        ):
            try:
                self.provider._send_api_request("GET", "/dummy")
            except Exception as e:
                self.assertNotIsInstance(e, JSONDecodeError)
                self.assertIsInstance(e, ValidationError)
                self.assertIn("Cloudflare Error", e.args[0])
