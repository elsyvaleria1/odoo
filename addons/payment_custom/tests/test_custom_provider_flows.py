
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment_custom import const
from odoo.addons.payment_custom.controllers.main import CustomController
from odoo.addons.payment_custom.tests.common import PaymentCustomCommon


@tagged("-at_install", "post_install")
class TestCustomProviderFlows(PaymentCustomCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls._prepare_provider(code="custom", custom_mode="wire_transfer")

    def test_rendering_values_expose_process_url_and_reference(self):
        tx = self._create_transaction(flow="direct", reference="RENDER-REF")

        values = tx._prepare_redirect_form_values({})

        self.assertEqual(values["api_url"], CustomController._process_url)
        self.assertEqual(values["reference"], "RENDER-REF")

    def test_default_payment_method_codes_for_wire_transfer(self):
        self.assertEqual(
            self.provider._get_default_payment_method_codes(),
            const.DEFAULT_PAYMENT_METHOD_CODES,
        )

    def test_amount_validation_skipped_for_custom(self):
        tx = self._create_transaction(flow="direct", reference="AMOUNT-REF")

        self.assertIsNone(tx._extract_amount_data({"amount": 999999.0}))

    def test_apply_updates_sets_pending(self):
        tx = self._create_transaction(flow="direct", reference="PENDING-REF")
        self.assertEqual(tx.state, "draft")

        tx._apply_updates({})

        self.assertEqual(tx.state, "pending")

    def test_sent_message_names_the_provider(self):
        tx = self._create_transaction(flow="direct", reference="SENT-REF")

        self.assertIn(tx.provider_id.name, tx._get_sent_message())

    def test_provider_domain_filters_by_custom_mode(self):
        domain = self.env["payment.provider"]._get_domain_provider(
            "custom", custom_mode="wire_transfer"
        )

        providers = self.env["payment.provider"].search(domain)
        self.assertIn(self.provider, providers)

    def test_removal_values_nullify_custom_mode(self):
        self.assertIsNone(
            self.env["payment.provider"]._prepare_removal_values()["custom_mode"]
        )

    def test_custom_mode_required_for_custom_provider(self):
        with self.assertRaises(ValidationError):
            self.provider.custom_mode = False

    def test_recompute_pending_msg_degrades_without_account_payment(self):
        if (
            self.env["ir.module.module"]._get("account_payment_provider").state
            == "installed"
        ):
            self.skipTest("account_payment installed: recompute would rewrite")
        self.provider.pending_msg = "<p>keep me</p>"

        self.provider.action_recompute_pending_msg()

        self.assertEqual(self.provider.pending_msg, "<p>keep me</p>")

    def test_ensure_pending_msg_targets_only_empty_wire_providers(self):
        self.provider.pending_msg = False

        self.provider._transfer_update_missing_pending_msg()

        if "account_payment_provider" in self.env.registry.loaded_modules:
            self.assertTrue(self.provider.pending_msg)
        else:
            self.assertFalse(self.provider.pending_msg)

    def test_qr_code_degrades_without_account(self):
        if self.env["ir.module.module"]._get("account").state == "installed":
            self.skipTest(
                "account installed: prepare_qr_code_base64 would be available"
            )
        self.provider.qr_code = True
        tx = self._create_transaction(flow="direct", reference="QR-REF")

        self.assertFalse(self.company.partner_id.bank_account_ids)
        self.assertIsNone(tx._get_custom_qr_code())

        self.env["res.partner.bank.account"].create(
            {
                "acc_number": "FR1420041010050500013M02606",
                "partner_id": self.company.partner_id.id,
            }
        )
        self.company.partner_id.invalidate_recordset(["bank_account_ids"])

        self.assertTrue(self.company.partner_id.bank_account_ids)
        self.assertIsNone(tx._get_custom_qr_code())

    def test_qr_code_none_when_disabled(self):
        self.provider.qr_code = False
        tx = self._create_transaction(flow="direct", reference="QR-DISABLED-REF")

        self.assertIsNone(tx._get_custom_qr_code())

    def test_create_wire_transfer_clears_pending_msg(self):
        provider = self.env["payment.provider"].create(
            {
                "name": "Fresh wire transfer",
                "code": "custom",
                "custom_mode": "wire_transfer",
                "pending_msg": "<p>preset message</p>",
            },
        )
        self.assertFalse(provider.pending_msg)
