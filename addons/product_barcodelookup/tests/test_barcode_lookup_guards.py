from unittest.mock import MagicMock, patch

from odoo.exceptions import RedirectWarning, UserError
from odoo.libs.guarded_http import GuardedSession
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.product_barcodelookup.tools import barcode_lookup_service

PNG_1PX = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    b"YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestBarcodeLookupGuards(TransactionCase):
    def _set_api_key(self, value):
        self.env["credential.credential"]._set_system_secret(
            "product_barcodelookup.api_key", value
        )

    def test_lookup_key_reads_config_parameter(self):
        self._set_api_key("secret-key")
        self.assertEqual(
            barcode_lookup_service.get_barcode_lookup_key(self.env["product.product"]),
            "secret-key",
        )
        self._set_api_key(False)
        self.assertFalse(
            barcode_lookup_service.get_barcode_lookup_key(self.env["product.product"])
        )

    def test_lookup_request_status_branches(self):
        ok_response = MagicMock(status_code=200)
        with patch.object(GuardedSession, "get", return_value=ok_response):
            self.assertIs(
                barcode_lookup_service.barcode_lookup_request("http://x"), ok_response
            )
        with patch.object(
            GuardedSession,
            "get",
            return_value=MagicMock(status_code=404),
        ):
            self.assertEqual(
                barcode_lookup_service.barcode_lookup_request("http://x"),
                {"authenticated": True, "status_code": 404},
            )
        with patch.object(
            GuardedSession,
            "get",
            return_value=MagicMock(status_code=500),
        ):
            self.assertEqual(
                barcode_lookup_service.barcode_lookup_request("http://x"),
                {"status_code": 500},
            )

    def test_check_api_key_set_redirects_when_missing(self):
        self._set_api_key(False)
        with self.assertRaises(RedirectWarning):
            self.env["wizard.product.product.update.image"]._check_api_key_set()

    def test_check_cron_status_blocks_on_pending_trigger(self):
        wizard_model = self.env["wizard.product.product.update.image"]
        self.assertTrue(wizard_model._check_cron_status())

        cron = self.env.ref("product_barcodelookup.ir_cron_fetch_image")
        self.env["ir.cron.trigger"].create(
            {"cron_id": cron.id, "call_at": self.env.cr.now()}
        )
        with self.assertRaises(UserError):
            wizard_model._check_cron_status()

    def test_default_get_classifies_products(self):
        self._set_api_key("secret-key")
        processable, unprocessable = self.env["product.product"].create(
            [
                {"name": "No Image", "barcode": "7501000000001"},
                {
                    "name": "Has Image",
                    "barcode": "7501000000002",
                    "image_1920": PNG_1PX,
                },
            ]
        )
        defaults = (
            self.env["wizard.product.product.update.image"]
            .with_context(
                active_model="product.product",
                active_ids=[processable.id, unprocessable.id],
            )
            .default_get(["products_to_process"])
        )
        self.assertEqual(defaults["nb_products_selected"], 2)
        self.assertEqual(defaults["nb_products_to_process"], 1)
        self.assertEqual(defaults["nb_products_unable_to_process"], 1)
        self.assertEqual(defaults["products_to_process"], processable)
