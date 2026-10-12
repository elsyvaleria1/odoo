from unittest.mock import patch

from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.whatsapp.tests.common import WhatsAppCommon


@tagged("post_install", "-at_install")
class TestWhatsAppCredentials(WhatsAppCommon):
    def test_writing_a_secret_creates_a_credential_and_stores_it_there(self):
        account = self.env["whatsapp.account"].create(
            {
                "name": "Vault Account",
                "app_uid": "APP",
                "account_uid": "ACC",
                "phone_uid": "PHONE",
                "notify_user_ids": self.user_wa_admin.ids,
                "app_secret": "the-app-secret",
                "token": "the-bearer",
            }
        )
        self.assertTrue(account.credential_id, "a secret creates the credential")
        held = json_loads(account.credential_id.sudo().credential_data)
        self.assertEqual(held["app_secret"], "the-app-secret")
        self.assertEqual(held["token"], "the-bearer")

    def test_the_fields_read_back_what_was_written(self):
        account = self._vault_account()
        account.invalidate_recordset()
        self.assertEqual(account.app_secret, "s3cret")
        self.assertEqual(account.token, "b3arer")

    def test_the_three_secrets_share_one_credential(self):
        account = self._vault_account()
        self.assertTrue(account.webhook_verify_token)
        held = json_loads(account.credential_id.sudo().credential_data)
        self.assertEqual(
            sorted(held),
            ["app_secret", "token", "webhook_verify_token"],
            "one Meta app registration is one credential record",
        )

    def test_the_verify_token_is_minted_once_and_kept(self):
        account = self._vault_account()
        first = account.webhook_verify_token
        self.assertEqual(len(first), 8)
        account.invalidate_recordset()
        self.assertEqual(
            account.webhook_verify_token,
            first,
            "it is pasted into Meta's dashboard, so it must not change on read",
        )

    def test_reading_the_secrets_writes_nothing(self):
        account = self._vault_account()
        account.invalidate_recordset()
        with patch.object(
            type(account),
            "_wa_store_secret",
            side_effect=AssertionError("reading a secret must not store one"),
        ):
            self.assertEqual(account.token, "b3arer")
            self.assertEqual(len(account.webhook_verify_token), 8)

    def test_the_first_secret_brings_the_verify_token(self):
        account = self.env["whatsapp.account"].create(
            {
                "name": "Bare Account",
                "app_uid": "BARE",
                "account_uid": "BARE",
                "phone_uid": "BARE",
                "notify_user_ids": self.user_wa_admin.ids,
            }
        )
        self.assertFalse(account.webhook_verify_token)

        account.token = "first-bearer"

        self.assertEqual(len(account.webhook_verify_token), 8)

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'whatsapp_account'
               AND column_name IN ('app_secret', 'token', 'webhook_verify_token')
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the columns; a nulled column still shows up in "
            "every backup taken before it was nulled, and these two carried "
            "NOT NULL besides",
        )

    def test_an_account_with_no_credential_reads_empty_rather_than_raising(self):
        account = self.env["whatsapp.account"].create(
            {
                "name": "Bare Account",
                "app_uid": "APP",
                "account_uid": "ACC",
                "phone_uid": "PHONE",
                "notify_user_ids": self.user_wa_admin.ids,
            }
        )
        self.assertFalse(account.credential_id)
        self.assertFalse(account.app_secret)
        self.assertFalse(account.token)

    def test_the_webhook_lookup_finds_the_account_by_its_verify_token(self):
        account = self._vault_account()
        found = (
            self.env["whatsapp.account"]
            .search([])
            .filtered(lambda a: a.webhook_verify_token == account.webhook_verify_token)
        )
        self.assertIn(account, found)

    def _vault_account(self):
        return self.env["whatsapp.account"].create(
            {
                "name": "Vault Account",
                "app_uid": "APP",
                "account_uid": "ACC",
                "phone_uid": "PHONE",
                "notify_user_ids": self.user_wa_admin.ids,
                "app_secret": "s3cret",
                "token": "b3arer",
            }
        )
