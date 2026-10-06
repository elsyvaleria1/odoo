from lxml import etree

from .common import TelegramBotTestCase


class TestPartnerFormPlacement(TelegramBotTestCase):
    def test_the_telegram_accounts_sit_in_the_main_contact_block(self):
        combined = self.env["res.partner"].get_view(
            self.env.ref("base.view_partner_form").id, "form"
        )["arch"]
        tree = etree.fromstring(combined.encode())
        nodes = tree.xpath("//field[@name='telegram_account_ids']")

        self.assertEqual(len(nodes), 1)
        self.assertTrue(
            nodes[0].xpath("ancestor::div[@name='partner_phone_row']"),
            "the accounts must sit beside the phone, not in a subview",
        )
        self.assertEqual(len(tree.xpath("//button[@name='action_telegram_invite']")), 1)
