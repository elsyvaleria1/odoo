from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.account_online_synchronization.tests.common import (
    AccountOnlineSynchronizationCommon,
)


@tagged("post_install", "-at_install")
class TestOdooFinCredentials(AccountOnlineSynchronizationCommon):
    def test_the_fixture_tokens_landed_in_one_credential(self):
        credential = self.account_online_link.credential_id.sudo()

        self.assertTrue(credential)
        self.assertEqual(credential.oauth_access_token, "access_token")
        self.assertEqual(credential.oauth_refresh_token, "refresh_token")

    def test_the_fields_read_back_what_was_written(self):
        self.account_online_link.invalidate_recordset()

        self.assertEqual(self.account_online_link.access_token, "access_token")
        self.assertEqual(self.account_online_link.refresh_token, "refresh_token")

    def test_fetching_a_new_access_token_leaves_the_refresh_token_alone(self):
        self.account_online_link.access_token = "a-newer-access-token"
        self.account_online_link.invalidate_recordset()

        self.assertEqual(self.account_online_link.access_token, "a-newer-access-token")
        self.assertEqual(
            self.account_online_link.refresh_token,
            "refresh_token",
            "fetching an access token must not discard the token that signs for it",
        )

    def test_an_accountant_still_reads_the_access_token(self):
        accountant = self.env["res.users"].create(
            {
                "name": "Plain Accountant",
                "login": "plain_accountant_probe",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_basic").id])],
            }
        )
        link = self.account_online_link.with_user(accountant)
        link.invalidate_recordset()

        self.assertEqual(link.access_token, "access_token")

    def test_an_accountant_still_cannot_read_the_refresh_token(self):
        accountant = self.env["res.users"].create(
            {
                "name": "Plain Accountant Two",
                "login": "plain_accountant_probe_2",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_basic").id])],
            }
        )
        link = self.account_online_link.with_user(accountant)
        link.invalidate_recordset()

        with self.assertRaises(AccessError):
            link.read(["refresh_token"])

    def test_an_accountant_can_still_read_the_record(self):
        accountant = self.env["res.users"].create(
            {
                "name": "Plain Accountant Three",
                "login": "plain_accountant_probe_3",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_basic").id])],
            }
        )
        link = self.account_online_link.with_user(accountant)
        link.invalidate_recordset()

        self.assertTrue(link.read(), "the list view reads the whole record")

    def test_clearing_both_unlinks_the_credential(self):
        credential = self.account_online_link.credential_id

        self.account_online_link.write({"access_token": False, "refresh_token": False})

        self.assertFalse(self.account_online_link.credential_id)
        self.assertFalse(credential.exists())

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'account_online_link'
               AND column_name IN ('access_token', 'refresh_token')
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the columns; a nulled one still sits in every "
            "backup taken before it was nulled",
        )
