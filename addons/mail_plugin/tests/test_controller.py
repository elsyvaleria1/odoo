import base64
import json
import time
from unittest.mock import Mock, patch

from odoo.exceptions import AccessError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import HttpCase, new_unbound_test_api_key
from odoo.tools import hmac, mute_logger

from odoo.addons.iap.tools import iap_tools
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_plugin.controllers.authenticate import AUTH_CODE_SCOPE
from odoo.addons.mail_plugin.tests.common import (
    TestMailPluginControllerCommon,
    as_outlook_user,
    outlook_api_key,
)


class TestMailPluginController(TestMailPluginControllerCommon):
    def test_enrich_and_create_company(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Test partner",
                "email": "test@test_domain.xyz",
                "is_company": False,
            }
        )

        result = self.mock_enrich_and_create_company(
            partner.id,
            lambda _, domain: {"return": domain},
        )

        self.assertEqual(result["enrichment_info"], {"type": "company_created"})
        self.assertEqual(
            result["company"]["additionalInfo"]["return"], "test_domain.xyz"
        )

        company_id = result["company"]["id"]
        company = self.env["res.partner"].browse(company_id)
        partner.invalidate_recordset()
        self.assertEqual(
            partner.parent_id, company, "Should change the company of the partner"
        )

    def test_a_key_bound_to_no_door_is_refused(self):
        def modules_get(key):
            return self.url_open(
                "/mail_client_extension/modules/get",
                data=json_dumps_bytes(
                    {"id": 0, "jsonrpc": "2.0", "method": "call", "params": {}}
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
            )

        outlook = modules_get(outlook_api_key(self.env, "employee"))
        self.assertEqual(outlook.json()["result"], {"modules": ["contacts", "crm"]})
        with mute_logger("odoo.http"):
            unbound = modules_get(new_unbound_test_api_key(self.user_test))
        body = unbound.json()
        self.assertNotIn("result", body)
        self.assertEqual(
            body["error"]["data"]["message"], "401 Unauthorized: Invalid apikey"
        )

    @as_outlook_user("employee")
    def test_get_partner_blacklisted_domain(self):
        domain = min(iap_tools._MAIL_PROVIDERS)

        data = {
            "id": 0,
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"email": "contact@" + domain, "name": "test"},
        }

        mocked_request_enrich = Mock()

        with patch(
            "odoo.addons.iap.models.iap_enrich_api.IapEnrichApi._request_enrich",
            new=mocked_request_enrich,
        ):
            result = (
                self.url_open(
                    "/mail_plugin/partner/get",
                    data=json_dumps_bytes(data),
                    headers={"Content-Type": "application/json"},
                )
                .json()
                .get("result", {})
            )

        self.assertFalse(mocked_request_enrich.called)
        self.assertEqual(result["partner"]["enrichment_info"]["type"], "missing_data")

    def test_get_partner_company_found(self):
        company = self.env["res.partner"].create(
            {
                "name": "Test partner",
                "email": "test@test_domain.xyz",
                "is_company": True,
            }
        )

        mock_iap_enrich = Mock()
        result = self.mock_plugin_partner_get(
            "Test", "qsd@test_domain.xyz", mock_iap_enrich
        )

        self.assertFalse(mock_iap_enrich.called)
        self.assertEqual(result["partner"]["id"], -1)
        self.assertEqual(result["partner"]["email"], "qsd@test_domain.xyz")
        self.assertEqual(result["partner"]["company"]["id"], company.id)
        self.assertFalse(result["partner"]["company"]["additionalInfo"])

    def test_get_partner_company_not_found(self):
        self.env["res.partner"].create(
            {
                "name": "Test partner",
                "email": "test@test_domain.xyz",
                "is_company": False,
            }
        )

        result = self.mock_plugin_partner_get(
            "Test",
            "qsd@test_domain.xyz",
            lambda _, domain: {"enrichment_info": "missing_data"},
        )

        self.assertEqual(result["partner"]["id"], -1)
        self.assertEqual(result["partner"]["email"], "qsd@test_domain.xyz")
        self.assertEqual(result["partner"]["company"]["id"], -1)

    def test_get_partner_iap_return_different_domain(self):
        result = self.mock_plugin_partner_get(
            "Test",
            "qsd@test_domain.xyz",
            lambda _, domain: {
                "name": "Name",
                "email": ["contact@gmail.com"],
                "iap_information": "test",
            },
        )

        first_company_id = result["partner"]["company"]["id"]
        first_company = self.env["res.partner"].browse(first_company_id)

        self.assertEqual(result["partner"]["id"], -1)
        self.assertEqual(result["partner"]["email"], "qsd@test_domain.xyz")
        self.assertTrue(first_company_id, "Should have created the company")
        self.assertEqual(
            result["partner"]["company"]["additionalInfo"]["iap_information"], "test"
        )

        self.assertEqual(first_company.name, "Name")
        self.assertEqual(first_company.email, "contact@gmail.com")

        mock_iap_enrich = Mock()
        result = self.mock_plugin_partner_get(
            "Test", "qsd@test_domain.xyz", mock_iap_enrich
        )
        self.assertFalse(
            mock_iap_enrich.called,
            "We already enriched this company, should not call IAP a second time",
        )

        second_company_id = result["partner"]["company"]["id"]
        self.assertEqual(
            first_company_id, second_company_id, "Should not create a new company"
        )
        self.assertEqual(
            result["partner"]["company"]["additionalInfo"]["iap_information"], "test"
        )

    def test_get_partner_no_access(self):
        partner = self.env["res.partner"].create(
            {"name": "Test", "website": "https://test.example.com"}
        )
        partner_count = self.env["res.partner"].search_count([])
        self.env["res.partner.iap"].create(
            {
                "partner_id": partner.id,
                "iap_search_domain": "@test.example.com",
            }
        )

        result = self.mock_plugin_partner_get(
            "Test",
            "test@test.example.com",
            lambda _, domain: {"name": "Name", "email": "test@test.example.com"},
        )
        self.assertEqual(
            result["partner"]["company"]["website"], "https://test.example.com"
        )
        new_partner_count = self.env["res.partner"].search_count([])
        self.assertEqual(
            new_partner_count, partner_count, "Should not have created a new partner"
        )

        def _get_records_forbidden_and_error_factory(record, operation):
            if operation == "read" and record == partner:
                return record, lambda: AccessError("No Access")
            return None

        with patch.object(
            type(partner),
            "_get_records_forbidden_and_error_factory",
            _get_records_forbidden_and_error_factory,
        ):
            result = self.mock_plugin_partner_get(
                "Test",
                "test@test.example.com",
                lambda _, domain: {"name": "Name", "email": "test@test.example.com"},
            )
        self.assertEqual(result["partner"]["company"].get("id"), partner.id)
        self.assertEqual(result["partner"]["company"].get("name"), "No Access")
        self.assertFalse(result["partner"]["company"].get("website"))
        new_partner_count = self.env["res.partner"].search_count([])
        self.assertEqual(
            new_partner_count, partner_count, "Should not have created a new partner"
        )

    def test_get_partner_no_email_returned_by_iap(self):
        result = self.mock_plugin_partner_get(
            "Test",
            "qsd@domain.com",
            lambda _, domain: {"name": "Name", "email": []},
        )

        first_company_id = result["partner"]["company"]["id"]
        self.assertTrue(first_company_id and first_company_id > 0)

        first_company = self.env["res.partner"].browse(first_company_id)
        self.assertEqual(first_company.name, "Name")
        self.assertFalse(first_company.email)

        result = self.mock_plugin_partner_get(
            "Test",
            "qsd@domain.com",
            lambda _, domain: {"name": "Name", "email": ["contact@" + domain]},
        )
        second_company_id = result["partner"]["company"]["id"]
        self.assertEqual(
            first_company_id, second_company_id, "Should not create a new company"
        )

    def test_get_partner_is_default_from(self):
        self.env["mail.alias.domain"].create(
            {"name": "example.com", "default_from": "notification"}
        )
        mock_iap_enrich = Mock()
        result = self.mock_plugin_partner_get(
            "Test partner", "notificaTION@EXAMPLE.COM", mock_iap_enrich
        )
        self.assertEqual(
            result,
            {
                "partner": {
                    "name": "Notification",
                    "email": "notification@example.com",
                    "enrichment_info": {
                        "type": "odoo_custom_error",
                        "info": "This is your notification address. Search the Contact manually to link this email to a record.",
                    },
                },
            },
        )


class TestMailPluginAuthCode(HttpCase):
    def _redeem(self, auth_code):
        return self.url_open(
            "/mail_plugin/auth/access_token",
            data=json_dumps_bytes(
                {
                    "id": 0,
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {"auth_code": auth_code},
                }
            ),
            headers={"Content-Type": "application/json"},
        ).json()

    def test_an_auth_code_the_confirm_route_signs_is_redeemed_for_a_key(self):
        user = mail_new_test_user(self.env, login="plugin_user")
        message = json.dumps(
            {
                "name": "plugin",
                "scope": "outlook",
                "timestamp": int(time.time()),
                "uid": user.id,
            },
            sort_keys=True,
        ).encode()
        signature = hmac(self.env(su=True), AUTH_CODE_SCOPE, message).encode()
        auth_code = (
            f"{base64.b64encode(message).decode()}."
            f"{base64.b64encode(signature).decode()}"
        )
        self.assertIn("access_token", self._redeem(auth_code)["result"])

    def test_a_malformed_auth_code_is_refused_as_an_invalid_code(self):
        for auth_code in (
            "no-dot",
            "a.b.c",
            "!!!.!!!",
            "é.é",
            base64.b64encode(b"{}").decode() + ".",
            base64.b64encode(b"{}").decode() + "." + base64.b64encode(b"\xff").decode(),
            42,
            ["code"],
        ):
            with self.subTest(auth_code=auth_code):
                self.assertEqual(
                    self._redeem(auth_code).get("result"), {"error": "Invalid code"}
                )
