from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.sale_amazon.tests.common import TestAmazonCommon


@tagged("post_install", "-at_install")
class TestAmazonCredentials(TestAmazonCommon):
    """The LWA refresh token rests in the vault and the field is a door (ADR-0081).

    `access_token` and `restricted_data_token` are `store=False` and are not
    part of this: they live for one request and are refreshed by an API call, so
    there is no column and nothing to move.
    """

    def test_writing_the_token_creates_a_credential_and_stores_it_there(self):
        self.account.refresh_token = "Atzr|a-refresh-token"
        self.assertTrue(self.account.credential_id)
        self.assertEqual(
            self.account.credential_id.sudo().credential_value, "Atzr|a-refresh-token"
        )

    def test_the_field_reads_back_what_was_written(self):
        self.account.refresh_token = "Atzr|round-trip"
        self.account.invalidate_recordset()
        self.assertEqual(self.account.refresh_token, "Atzr|round-trip")

    def test_holding_a_credential_is_what_connected_means(self):
        self.account.refresh_token = "Atzr|connect-me"
        self.assertEqual(self.account.state, "connected")

    def test_resetting_the_token_unlinks_the_credential_and_disconnects(self):
        self.account.refresh_token = "Atzr|to-be-reset"
        credential = self.account.credential_id
        self.account.action_reset_refresh_token()

        self.assertFalse(self.account.credential_id)
        self.assertEqual(self.account.state, "disconnected")
        self.assertFalse(
            credential.exists(),
            "a disconnected account keeps no credential behind it",
        )

    def test_an_account_with_no_credential_reads_empty(self):
        # The shared fixture creates its account already holding a token, so a
        # never-connected account has to be made here.
        account = self.env["amazon.account"].create(
            {
                "name": "NeverConnected",
                "seller_key": "Another Seller Key",
                "base_marketplace_id": self.marketplace.id,
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(account.credential_id)
        self.assertFalse(account.refresh_token)
        self.assertEqual(account.state, "disconnected")

    def test_the_offer_domain_selects_on_the_credential(self):
        # `('refresh_token', '!=', False)` could not survive the field becoming a
        # door: an unstored compute is not searchable. The credential is.
        self.account.refresh_token = "Atzr|searchable"
        found = self.env["amazon.account"].search([("credential_id", "!=", False)])
        self.assertIn(self.account, found)

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'amazon_account' AND column_name = 'refresh_token'
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the column; a nulled one still sits in every "
            "backup taken before it was nulled",
        )

    def test_the_short_lived_tokens_are_still_unstored(self):
        self.assertFalse(self.env["amazon.account"]._fields["access_token"].store)
        self.assertFalse(
            self.env["amazon.account"]._fields["restricted_data_token"].store
        )

    def _sale_manager(self):
        return self.env["res.users"].create(
            {
                "name": "Sale Manager Only",
                "login": "sale_manager_no_system",
                "group_ids": [(6, 0, [self.env.ref("sale.group_sale_manager").id])],
            }
        )

    def test_a_sale_manager_reads_the_account_but_not_the_token(self):
        # This group owns the model (an ir.access permission grants it CRUD), so every
        # ordinary flow runs as it. `state` has to survive; the secret must not.
        account = self.account.with_user(self._sale_manager())
        account.invalidate_recordset()

        self.assertTrue(account.read(), "the list view reads the whole record")
        self.assertEqual(account.state, "connected")
        with self.assertRaises(AccessError):
            account.read(["refresh_token"])

    def test_a_sale_manager_can_still_disconnect(self):
        account = self.account.with_user(self._sale_manager())
        account.action_reset_refresh_token()
        self.assertEqual(account.state, "disconnected")

    def test_the_setup_check_answers_for_a_sale_manager(self):
        from odoo.addons.sale_amazon import utils as amazon_utils

        account = self.account.with_user(self._sale_manager())
        account.action_reset_refresh_token()
        with self.assertRaises(UserError):
            amazon_utils.check_account_is_set_up(account, require_marketplaces=False)
