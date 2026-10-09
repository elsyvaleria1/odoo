import re
from datetime import timedelta

from odoo import fields
from odoo.tests import freeze_time, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon
from odoo.addons.mail.tests.common import MockEmail


@tagged("post_install", "-at_install")
class TestCustomerConfirmation(CollectionCommon, MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a.write({"email": "sauce@example.com", "lang": "en_US"})
        cls.company_data[
            "company"
        ].account_config_id.collection_supervisor_id = cls.treasurer
        cls.public = cls.env.ref("base.public_user")

    def _collect_with_mails(self, partner=None):
        with self.mock_mail_gateway():
            payment = self._collect(self._post_invoice(1000.0, partner=partner), 1000.0)
            mails = self._new_mails
        return payment.with_env(self.env), mails

    def _delivery(self, payment):
        challenge = payment._get_confirmation_challenges()[payment.id]
        return challenge.delivery_ids.with_env(self.env)

    def _supervisor_activities(self, payment):
        return payment.activity_ids.filtered(
            lambda activity: activity.user_id == self.treasurer
        )

    def test_a_posted_collection_asks_its_customer_instead_of_a_plain_receipt(self):
        payment, mails = self._collect_with_mails()

        self.assertEqual(payment.confirmation_state, "pending")
        (mail,) = mails
        self.assertEqual(mail.subject, "Please confirm")
        self.assertEqual(mail.email_to, self.partner_a.email_formatted)
        self.assertIn("1,000.00", mail.body_html)
        self.assertIn(self.collector.name, mail.body_html)
        self.assertIn(f"/collection/receipt/{payment.id}", mail.body_html)
        self.assertIn("/proof/answer/", mail.body_html)

    def test_the_customer_confirms_from_outside(self):
        payment, _mails = self._collect_with_mails()

        self._delivery(payment).with_user(self.public)._answer("confirmed")

        self.assertEqual(payment.confirmation_state, "confirmed")
        self.assertEqual(payment.confirmation_sent_to, "s****@example.com")
        self.assertTrue(payment.confirmation_date)
        self.assertTrue(payment._is_confirmation_current())
        self.assertIn("I confirm this collection", payment.message_ids[0].body)
        self.assertEqual(payment.message_ids[0].author_id, self.partner_a)
        self.assertFalse(self._supervisor_activities(payment))

    def test_a_dispute_reaches_the_supervisor_with_its_reason(self):
        payment, _mails = self._collect_with_mails()

        self._delivery(payment).with_user(self.public)._answer(
            "disputed", reason="I paid 1,200"
        )

        self.assertEqual(payment.confirmation_state, "disputed")
        (activity,) = self._supervisor_activities(payment)
        self.assertIn("I paid 1,200", activity.note)
        self.assertIn("not right", payment.message_ids[0].body)

    def test_a_later_word_from_the_customer_is_noted(self):
        payment, _mails = self._collect_with_mails()
        evidence = self._delivery(payment)._answer("disputed")

        payment._on_confirmation_comment(evidence, "The collector kept 200")

        self.assertIn("The collector kept 200", payment.message_ids[0].body)

    def test_a_customer_no_channel_reaches_is_unreachable(self):
        partner = self.env["res.partner"].create({"name": "No Channels"})

        payment, mails = self._collect_with_mails(partner=partner)

        self.assertEqual(payment.confirmation_state, "unreachable")
        self.assertFalse(mails)

    def test_no_answer_in_time_reaches_the_supervisor(self):
        payment, _mails = self._collect_with_mails()

        with freeze_time(fields.Datetime.now() + timedelta(days=3, hours=1)):
            self.env["proof.challenge"]._cron_follow_up_confirmations()

        self.assertEqual(payment.confirmation_state, "expired")
        self.assertTrue(self._supervisor_activities(payment))

    def test_cancelling_takes_the_question_back(self):
        payment, _mails = self._collect_with_mails()
        delivery = self._delivery(payment)

        payment.action_cancel()

        self.assertFalse(payment.confirmation_state)
        self.assertEqual(delivery.sudo().state, "withdrawn")

    def test_with_the_customer_at_hand_a_code_confirms_it(self):
        payment, _mails = self._collect_with_mails()
        delivery = self._delivery(payment)
        collection = payment.with_user(self.collector)

        with self.mock_mail_gateway():
            params = collection.action_issue_confirmation_code()
            code_mail = self._new_mails
        code = re.search(r">\s*(\d{6})\s*<", code_mail.body_html).group(1)
        collection.action_prove_confirmation_code(
            {
                "token": params["token"],
                "method": "email_code",
                "payload": {"code": code},
            }
        )

        self.assertEqual(payment.confirmation_state, "confirmed")
        self.assertEqual(delivery.sudo().state, "withdrawn")
        self.assertIn("I confirm this collection", payment.message_ids[0].body)

    def test_the_remittance_counts_what_customers_have_not_confirmed(self):
        confirmed, _mails = self._collect_with_mails()
        self._delivery(confirmed)._answer("confirmed")
        disputed, _mails = self._collect_with_mails()
        self._delivery(disputed)._answer("disputed")
        pending, _mails = self._collect_with_mails()

        remittance = self.env["account.collection.remittance"].create(
            {
                "collector_id": self.collector.id,
                "destination_journal_id": self.till_journal.id,
                "payment_ids": [(6, 0, (confirmed | disputed | pending).ids)],
            }
        )

        self.assertEqual(
            (remittance.count_payment_unconfirmed, remittance.count_payment_disputed),
            (2, 1),
        )

    def test_a_payment_outside_custody_asks_nobody(self):
        invoice = self._post_invoice(500.0)
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": invoice.partner_id.id,
                "amount": 500.0,
                "journal_id": self.bank_journal.id,
            }
        )

        payment.action_post()

        self.assertFalse(payment.confirmation_state)
