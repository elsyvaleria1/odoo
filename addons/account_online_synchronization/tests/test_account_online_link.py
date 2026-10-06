from odoo import Command
from odoo.tests import tagged

from odoo.addons.account_online_synchronization.tests.common import (
    AccountOnlineSynchronizationCommon,
)


@tagged("post_install", "-at_install")
class TestAccountOnlineLink(AccountOnlineSynchronizationCommon):
    def test_action_new_synchronization(self):
        def _get_latest_link():
            return self.env["account.online.link"].search(
                [], order="create_date, id desc", limit=1
            )

        def _assert_link_count(count, message):
            self.assertEqual(
                self.env["account.online.link"].search_count([]),
                count,
                message,
            )

        link_count = self.env["account.online.link"].search_count([])

        self.env["account.online.link"].action_new_synchronization()
        link_count += 1
        _assert_link_count(
            link_count,
            "A new account online link should have been created.",
        )

        link = _get_latest_link()
        link["provider_type"] = "some_provider"
        self.env["account.online.link"].action_new_synchronization()
        link_count += 1
        _assert_link_count(
            link_count,
            "A new account online link should have been created since there are no links without a provider type",
        )

        link = _get_latest_link()
        link["provider_type"] = False
        link["account_online_account_ids"] = [
            Command.create(
                {
                    "name": "Some Account",
                }
            ),
        ]
        self.env["account.online.link"].action_new_synchronization()
        link_count += 1
        _assert_link_count(
            link_count,
            "A new account online link should have been created since there are no links without account_online_account_ids",
        )

        link.action_new_synchronization()
        _assert_link_count(
            link_count,
            "No new account online link should have been created since the recordset contains one",
        )

    def test_batch_post_is_logged_on_every_linked_journal(self):
        journal_2 = self.env["account.journal"].create(
            {"name": "Second Bank Journal", "type": "bank", "code": "SBJ2"}
        )
        link_2 = self.env["account.online.link"].create(
            {"name": "Second Bank", "client_id": "client_id_2"}
        )
        self.env["account.online.account"].create(
            {
                "name": "Second Account",
                "account_online_link_id": link_2.id,
                "journal_ids": [Command.set(journal_2.ids)],
            }
        )
        links = self.account_online_link | link_2
        links._message_post_values_all(
            {link.id: {"body": "Consent renewed"} for link in links}
        )
        for journal in self.euro_bank_journal | journal_2:
            self.assertIn("<p>Consent renewed</p>", journal.message_ids.mapped("body"))
