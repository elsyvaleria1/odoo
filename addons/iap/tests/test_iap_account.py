import hashlib
import os
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.iap.models import iap_account as iap_account_module
from odoo.addons.iap.tools import iap_tools
from odoo.addons.mixin_encryption.models import mixin_encryption as encryption_module


@tagged("post_install", "-at_install")
class TestIapAccount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["iap.service"].search(
            [("technical_name", "=", "reveal")],
            limit=1,
        )

    def test_create_defaults_name_to_service(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        self.assertEqual(account.name, self.service.name)
        self.assertTrue(account.account_token)

    def test_create_on_neutralized_db_disables_token(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "database.is_neutralized",
            True,
        )
        account = self.env["iap.account"].create({"service_id": self.service.id})
        self.assertTrue(account.account_token.endswith("+disabled"))

    def test_the_token_lives_in_a_credential(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        credential = account.sudo().credential_id
        self.assertTrue(credential)
        self.assertEqual(
            credential._use_secret("iap:account_token").reveal(),
            account.sudo().account_token,
        )
        self.assertFalse(self.env["iap.account"]._fields["account_token"].store)

    def test_clearing_the_token_removes_its_credential(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        credential = account.sudo().credential_id
        account.sudo().account_token = False
        self.assertFalse(account.sudo().credential_id)
        self.assertFalse(credential.exists())

    def test_service_locked_blocks_service_change(self):
        other_service = self.env["iap.service"].search(
            [("technical_name", "!=", self.service.technical_name)],
            limit=1,
        )
        account = self.env["iap.account"].create(
            {"service_id": self.service.id, "service_locked": True}
        )
        with self.assertRaises(UserError):
            account.write({"service_id": other_service.id})

    def test_warning_threshold_must_be_positive(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        with self.assertRaises(UserError):
            account.warning_threshold = -1

    def test_positive_threshold_needs_a_recipient(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        with self.assertRaises(UserError):
            account.write(
                {"warning_threshold": 10, "warning_user_ids": [Command.clear()]}
            )

    def test_warning_recipients_need_email(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        no_mail = self.env["res.users"].create(
            {
                "name": "No mail",
                "login": "nomail_iap",
            }
        )
        no_mail.email = False
        with self.assertRaises(UserError):
            account.write(
                {
                    "warning_threshold": 10,
                    "warning_user_ids": [Command.set(no_mail.ids)],
                }
            )

    def test_warning_recipients_no_email_message_scoped_to_own_account(self):
        no_mail_a = self.env["res.users"].create(
            {"name": "No mail account A", "login": "nomail_iap_a"}
        )
        no_mail_a.email = False
        no_mail_b = self.env["res.users"].create(
            {"name": "No mail account B", "login": "nomail_iap_b"}
        )
        no_mail_b.email = False
        with self.assertRaises(UserError) as capture:
            self.env["iap.account"].create(
                [
                    {
                        "service_id": self.service.id,
                        "warning_threshold": 1,
                        "warning_user_ids": [Command.set(no_mail_a.ids)],
                    },
                    {
                        "service_id": self.service.id,
                        "warning_threshold": 1,
                        "warning_user_ids": [Command.set(no_mail_b.ids)],
                    },
                ]
            )
        self.assertIn(no_mail_a.name, str(capture.exception))
        self.assertNotIn(no_mail_b.name, str(capture.exception))

    def test_write_warning_fields_notifies_iap(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        recipient = self.env["res.users"].create(
            {
                "name": "Alert recipient",
                "login": "alert_iap",
                "email": "alert_iap@example.com",
            }
        )
        with patch.object(iap_tools, "iap_jsonrpc", return_value=True) as rpc:
            account.write(
                {
                    "warning_threshold": 25,
                    "warning_user_ids": [Command.set(recipient.ids)],
                }
            )
        self.assertTrue(rpc.called)
        called_kwargs = rpc.call_args.kwargs
        self.assertIn("/iap/1/update-warning-email-alerts", called_kwargs["url"])
        self.assertEqual(called_kwargs["params"]["warning_threshold"], 25)
        self.assertTrue(called_kwargs["params"]["warning_emails"][0]["email"])

    def test_acquire_creates_account_for_known_service(self):
        account = self.env["iap.account"].acquire_account("reveal")
        self.assertEqual(account.service_id, self.service)

    def test_acquire_unknown_service_raises(self):
        with self.assertRaises(UserError):
            self.env["iap.account"].acquire_account("no_such_service_technical_name")

    def test_acquire_without_a_vault_key_creates_no_account_and_logs_no_error(self):
        accounts = self.env["iap.account"]
        credentials = self.env["credential.credential"].sudo()
        credentials_before = credentials.search_count([])
        with patch.dict(os.environ, clear=False) as env:
            env.pop("ODOO_API_ENCRYPTION_KEY", None)
            with self.assertNoLogs(encryption_module._logger, "ERROR"):
                self.assertEqual(
                    accounts.acquire_account(
                        self.service.technical_name, force_create=False
                    ),
                    accounts,
                )
                with self.assertRaises(UserError) as caught:
                    accounts.acquire_account(self.service.technical_name)
        self.assertNotIsInstance(caught.exception, ValidationError)
        self.assertIn("ODOO_API_ENCRYPTION_KEY", str(caught.exception))
        self.assertFalse(accounts.search([("service_id", "=", self.service.id)]))
        self.assertEqual(credentials.search_count([]), credentials_before)

    def test_acquisition_without_creation_keeps_service_unregistered(self):
        accounts = self.env["iap.account"]
        self.assertFalse(accounts.search([("service_id", "=", self.service.id)]))
        self.assertEqual(
            accounts.acquire_account(self.service.technical_name, force_create=False),
            accounts,
        )
        self.assertEqual(accounts.get_credits(self.service.technical_name), 0)
        self.assertFalse(accounts.search([("service_id", "=", self.service.id)]))

    def test_hash_iap_token_ignores_suffix(self):
        expected = hashlib.sha1(b"abc").hexdigest()
        Account = self.env["iap.account"]
        self.assertEqual(Account._hash_iap_token("abc+disabled"), expected)
        self.assertEqual(Account._hash_iap_token("abc"), expected)

    def test_hash_iap_token_empty_raises(self):
        with self.assertRaises(UserError):
            self.env["iap.account"]._hash_iap_token("+disabled")

    def test_credits_url_carries_hashed_token(self):
        url = self.env["iap.account"].get_credits_url(
            "reveal",
            account_token="abc",
        )
        self.assertIn("service_name=reveal", url)
        self.assertIn(hashlib.sha1(b"abc").hexdigest(), url)
        self.assertNotIn("abc&", url)
        self.assertIn("hashed=1", url)

    def test_action_buy_credits_returns_url_action(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        action = account.action_buy_credits()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/iap/1/credit", action["url"])

    def test_get_credits_returns_balance(self):
        self.env["iap.account"].acquire_account("reveal")
        with patch.object(iap_tools, "iap_jsonrpc", return_value=42):
            self.assertEqual(self.env["iap.account"].get_credits("reveal"), 42)

    def test_get_credits_access_error_returns_minus_one(self):
        self.env["iap.account"].acquire_account("reveal")
        with patch.object(
            iap_tools,
            "iap_jsonrpc",
            side_effect=AccessError("down"),
        ):
            self.assertEqual(self.env["iap.account"].get_credits("reveal"), -1)

    def test_get_account_information_from_iap_syncs_balance_and_state(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        token = account.sudo().account_token
        fake_payload = {
            token: {
                "balance": 12.3456,
                "warning_threshold": 0,
                "registered": "registered",
            }
        }
        with (
            patch.object(iap_account_module.module, "current_test", False),
            patch.object(iap_tools, "iap_jsonrpc", return_value=fake_payload),
        ):
            account._update_account_information_from_iap()
        self.assertEqual(account.state, "registered")
        self.assertEqual(account.warning_threshold, 0)
        self.assertEqual(account.balance, "12 Credits")
        self.assertTrue(account.service_locked)

    def test_get_account_information_from_iap_positive_threshold_no_recipient(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        token = account.sudo().account_token
        fake_payload = {
            token: {
                "balance": 5,
                "warning_threshold": 10,
                "registered": "registered",
            }
        }
        with (
            patch.object(iap_account_module.module, "current_test", False),
            patch.object(iap_tools, "iap_jsonrpc", return_value=fake_payload),
        ):
            account._update_account_information_from_iap()
        self.assertEqual(account.warning_threshold, 10)
        self.assertFalse(account.warning_user_ids)

    def test_an_account_without_token_does_not_stop_the_sync_of_the_others(self):
        account = self.env["iap.account"].create({"service_id": self.service.id})
        tokenless = self.env["iap.account"].create({"service_id": self.service.id})
        tokenless.sudo().account_token = False
        fake_payload = {
            account.sudo().account_token: {
                "balance": 3,
                "warning_threshold": 0,
                "registered": "registered",
            }
        }
        with (
            patch.object(iap_account_module.module, "current_test", False),
            patch.object(iap_tools, "iap_jsonrpc", return_value=fake_payload),
        ):
            (tokenless | account)._update_account_information_from_iap()
        self.assertEqual(account.state, "registered")
        self.assertNotEqual(tokenless.state, "registered")
