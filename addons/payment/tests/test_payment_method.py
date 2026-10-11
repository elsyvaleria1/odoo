from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment.tests.common import PaymentCommon


@tagged("-at_install", "post_install")
class TestPaymentMethod(PaymentCommon):
    def test_unlinking_payment_method_from_provider_state_archives_tokens(self):
        token = self._create_token()
        self.payment_method.provider_ids = [
            Command.unlink(self.payment_method.provider_ids[:1].id)
        ]
        self.assertFalse(token.active)

    def test_payment_method_requires_provider_to_be_activated(self):
        self.provider.state = "disabled"
        with self.assertRaises(UserError):
            self.payment_methods.active = True

    def test_brand_compatible_with_manual_capture(self):
        self.provider.update(
            {
                "capture_manually": True,
                "support_manual_capture": "partial",
            }
        )
        self.payment_method.support_manual_capture = "partial"
        brand_payment_method = self.env["payment.method"].create(
            {
                "image": self.payment_method.image,
                "name": "Dummy Brand",
                "code": "dumbrand",
                "primary_payment_method_id": self.payment_method.id,
                "active": False,
                "provider_ids": self.provider.ids,
            }
        )
        self._assert_does_not_raise(
            ValidationError, brand_payment_method.action_unarchive
        )
        self.assertTrue(brand_payment_method.active)

    def test_unlink_not_allowed_when_linked_to_providers(self):
        payment_method_with_provider = self.env["payment.method"].create(
            {
                "image": self.payment_method.image,
                "name": "Dummy Method",
                "code": "dummymethod",
                "provider_ids": self.provider.ids,
            }
        )
        with self.assertRaises(UserError):
            payment_method_with_provider.unlink()

    def test_unlink_allowed_when_not_linked_to_providers(self):
        payment_method_without_provider = self.env["payment.method"].create(
            {
                "image": self.payment_method.image,
                "name": "Dummy Method",
                "code": "dummymethod",
                "provider_ids": [],
            }
        )
        self._assert_does_not_raise(UserError, payment_method_without_provider.unlink)

    def test_payment_method_compatible_when_provider_is_enabled(self):
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_not_compatible_when_provider_is_disabled(self):
        self.provider.state = "disabled"
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertNotIn(self.payment_method, compatible_payment_methods)

    def test_non_primary_payment_method_not_compatible(self):
        brand_payment_method = self.payment_method.copy()
        brand_payment_method.primary_payment_method_id = (
            self.payment_method_id
        )
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertNotIn(brand_payment_method, compatible_payment_methods)

    def test_payment_method_compatible_with_supported_countries(self):
        belgium = self.env.ref("base.be")
        self.payment_method.supported_country_ids = [Command.set([belgium.id])]
        self.partner.country_id = belgium
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_not_compatible_with_unsupported_countries(self):
        belgium = self.env.ref("base.be")
        self.payment_method.supported_country_ids = [Command.set([belgium.id])]
        france = self.env.ref("base.fr")
        self.partner.country_id = france
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertNotIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_compatible_when_no_supported_countries_set(self):
        self.payment_method.supported_country_ids = [Command.clear()]
        belgium = self.env.ref("base.be")
        self.partner.country_id = belgium
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(self.provider.ids, self.partner.id)
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_compatible_with_supported_currencies(self):
        self.payment_method.supported_currency_ids = [
            Command.set([self.currency_euro.id])
        ]
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, currency_id=self.currency_euro.id
        )
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_not_compatible_with_unsupported_currencies(self):
        self.payment_method.supported_currency_ids = [
            Command.set([self.currency_euro.id])
        ]
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, currency_id=self.currency_usd.id
        )
        self.assertNotIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_compatible_when_no_supported_currencies_set(self):
        self.payment_method.supported_currency_ids = [Command.clear()]
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, currency_id=self.currency_euro.id
        )
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_compatible_when_tokenization_forced(self):
        self.payment_method.support_tokenization = True
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, force_tokenization=True
        )
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_not_compatible_when_tokenization_forced(self):
        self.payment_method.support_tokenization = False
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, force_tokenization=True
        )
        self.assertNotIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_compatible_with_express_checkout(self):
        self.payment_method.support_express_checkout = True
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, is_express_checkout=True
        )
        self.assertIn(self.payment_method, compatible_payment_methods)

    def test_payment_method_not_compatible_with_express_checkout(self):
        self.payment_method.support_express_checkout = False
        compatible_payment_methods = self.env[
            "payment.method"
        ]._get_compatible_payment_methods(
            self.provider.ids, self.partner.id, is_express_checkout=True
        )
        self.assertNotIn(self.payment_method, compatible_payment_methods)

    def test_availability_report_covers_all_reasons(self):
        pms = self.env["payment.method"].search([("is_primary", "=", True)])
        pms.active = False

        self.payment_method.write(
            {
                "active": True,
                "support_express_checkout": True,
                "support_tokenization": True,
            }
        )

        report = {}
        payment_utils.add_to_report(report, self.provider)

        unavailable_provider = self.provider.copy()
        payment_utils.add_to_report(
            report, unavailable_provider, available=False, reason="test"
        )
        no_provider_pm = self.payment_method.copy()
        no_provider_pm.provider_ids = [Command.set([unavailable_provider.id])]
        unavailable_provider.payment_method_ids = [Command.set([no_provider_pm.id])]

        invalid_country_pm = self.payment_method.copy()
        belgium = self.env.ref("base.be")
        invalid_country_pm.supported_country_ids = [Command.set([belgium.id])]
        france = self.env.ref("base.fr")
        self.partner.country_id = france

        invalid_currency_pm = self.payment_method.copy()
        invalid_currency_pm.supported_currency_ids = [
            Command.set([self.currency_euro.id])
        ]

        no_tokenization_pm = self.payment_method.copy()
        no_tokenization_pm.support_tokenization = False

        no_express_checkout_pm = self.payment_method.copy()
        no_express_checkout_pm.support_express_checkout = False

        self.env["payment.method"]._get_compatible_payment_methods(
            self.provider.ids,
            self.partner.id,
            currency_id=self.currency_usd.id,
            force_tokenization=True,
            is_express_checkout=True,
            report=report,
        )

        expected_pms_report = {
            self.payment_method: {
                "available": True,
                "reason": "",
                "supported_providers": [(self.provider, True)],
            },
            no_provider_pm: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["provider_not_available"],
                "supported_providers": [(unavailable_provider, False)],
            },
            invalid_country_pm: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["incompatible_country"],
                "supported_providers": [(self.provider, True)],
            },
            invalid_currency_pm: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["incompatible_currency"],
                "supported_providers": [(self.provider, True)],
            },
            no_tokenization_pm: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["tokenization_not_supported"],
                "supported_providers": [(self.provider, True)],
            },
            no_express_checkout_pm: {
                "available": False,
                "reason": REPORT_REASONS_MAPPING["express_checkout_not_supported"],
                "supported_providers": [(self.provider, True)],
            },
        }
        self.maxDiff = None
        self.assertDictEqual(report["payment_methods"], expected_pms_report)
