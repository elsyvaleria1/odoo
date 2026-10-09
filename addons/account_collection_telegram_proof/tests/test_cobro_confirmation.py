import re

from odoo.tests import tagged

from odoo.addons.account_collection_telegram.tests.common import CollectionTelegramCase
from odoo.addons.mail.tests.common import MockEmail


@tagged("post_install", "-at_install")
class TestCobroConfirmation(CollectionTelegramCase, MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.bot_username = "agromarin_test_bot"

    def _code_of(self, mails):
        return re.search(r">\s*(\d{6})\s*<", mails.body_html).group(1)

    def test_the_collector_learns_where_the_customer_was_asked(self):
        self.customer.email = "sauce@example.com"

        reply = self._collect_cash()

        payment = self._payments()
        self.assertEqual(payment.confirmation_state, "pending")
        self.assertIn(
            "Waiting for the customer to confirm it on s****@example.com", reply
        )
        self.assertNotIn("got the receipt", reply)

    def test_with_the_customer_at_hand_the_collector_types_their_code(self):
        self.customer.email = "sauce@example.com"
        self._collect_cash()
        payment = self._payments()

        with self.mock_mail_gateway():
            reply = self._press(f"cpf:code:{payment.id}")
            code = self._code_of(self._new_mails)
        self.assertIn("We sent the customer a code (s****@example.com)", reply)
        wrong = f"{(int(code) + 1) % 10**6:06d}"
        self.assertIn("not the one we sent", self._say(wrong))
        reply = self._say(code)

        self.assertIn(f"The customer confirmed collection <b>{payment.name}</b>", reply)
        self.assertEqual(payment.confirmation_state, "confirmed")

    def test_a_customer_no_channel_reaches_can_be_invited(self):
        reply = self._collect_cash()
        payment = self._payments()
        self.assertIn("No channel reaches the customer", reply)

        self._press(f"cpf:invite:{payment.id}")

        photo = self.env["telegram.message"].search(
            [("api_method", "=", "sendPhoto")], order="id desc", limit=1
        )
        self.assertEqual(photo.attachment_id.mimetype, "image/png")
        self.assertIn(self.customer.name, photo.caption)
        invitation = self.env["telegram.link.token"].search(
            [("partner_id", "=", self.customer.id)], order="id desc", limit=1
        )
        self.assertEqual(invitation.method, "invitation")
        self.assertEqual(invitation.create_uid, self.collector)

    def test_another_persons_button_is_refused(self):
        self._collect_cash()
        payment = self._payments()

        reply = self._press(f"cpf:code:{payment.id}", chat_id="588002")

        self.assertIn("no longer valid", reply)
