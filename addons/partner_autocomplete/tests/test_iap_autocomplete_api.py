from unittest.mock import patch

from odoo import modules
from odoo.tests import TransactionCase, tagged
from odoo.tools.iap import InsufficientCreditError


@tagged("post_install", "-at_install")
class TestIapAutocompleteApi(TransactionCase):
    def test_request_during_tests_does_not_report_insufficient_credit(self):
        self.assertTrue(modules.module.current_test, "expected to run inside a test")
        response, error = self.env[
            "iap.autocomplete.api"
        ]._request_partner_autocomplete(
            "search_by_name", {"query": "x", "query_country_code": "US"}
        )
        self.assertFalse(response)
        self.assertNotEqual(error, "Insufficient Credit")

    def test_request_reports_real_insufficient_credit(self):
        with patch.object(
            type(self.env["iap.autocomplete.api"]),
            "_contact_iap",
            side_effect=InsufficientCreditError("no credit"),
        ):
            response, error = self.env[
                "iap.autocomplete.api"
            ]._request_partner_autocomplete(
                "search_by_name", {"query": "x", "query_country_code": "US"}
            )
        self.assertFalse(response)
        self.assertEqual(error, "Insufficient Credit")
