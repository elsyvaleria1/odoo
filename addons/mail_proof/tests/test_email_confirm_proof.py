import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, freeze_time, new_test_user, tagged

from odoo.addons.mail.tests.common import MockEmail


class EmailConfirmCase(MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.collector = new_test_user(
            cls.env, login="mail_proof_collector", email="collector@agromarin.mx"
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Abarrotes Lupita", "email": "lupita@example.com"}
        )
        cls.subject = cls.env["res.partner"].create({"name": "Collection 7"})
        cls.facts = {"amount": "5000.00", "currency": "MXN", "collector": "Juan"}
        cls.summary = [["Amount", "$ 5,000.00"], ["Received by", "Juan"]]

    def _ask(self, partner=None):
        with self.mock_mail_gateway():
            challenge = (
                self.env["proof.challenge"]
                .with_user(self.collector)
                ._issue_confirmation(
                    self.subject,
                    "test.collection",
                    self.facts,
                    partner or self.customer,
                    summary=self.summary,
                    remind_after=timedelta(days=1),
                )
            )
            mails = self._new_mails
        return challenge.sudo(), mails

    def _link(self, mail):
        url = re.search(r'href="([^"]*/proof/answer/[^"]*)"', mail.body_html)
        link = urlparse(url.group(1).replace("&amp;", "&"))
        return f"{link.path}?{link.query}"


@tagged("post_install", "-at_install")
class TestEmailConfirmProof(EmailConfirmCase, TransactionCase):
    def test_the_contact_is_mailed_what_they_confirm_and_a_link(self):
        challenge, mail = self._ask()

        (delivery,) = challenge.delivery_ids
        self.assertEqual(challenge.method_ids.code, "email_confirm")
        self.assertEqual(mail.email_to, self.customer.email_formatted)
        self.assertIn("$ 5,000.00", mail.body_html)
        self.assertTrue(
            self._link(mail).startswith(f"/proof/answer/{delivery.id}?access_token=")
        )
        self.assertEqual(
            (delivery.state, delivery.sent_to), ("sent", "l*****@example.com")
        )

    def test_the_answer_is_chained_with_its_verdict(self):
        challenge, _mail = self._ask()

        evidence = challenge.delivery_ids._answer("disputed", reason=" I paid 500 ")

        self.assertEqual(
            (challenge.state, challenge.verdict, challenge.evidence_id),
            ("redeemed", "disputed", evidence),
        )
        self.assertEqual(challenge.delivery_ids.state, "answered")
        evidence = evidence.sudo()
        self.assertEqual(
            (evidence.user_id, evidence.partner_id, evidence.verdict),
            (self.collector, self.customer, "disputed"),
        )
        self.assertEqual(evidence.digest, challenge.digest)
        self.assertEqual(evidence.payload["reason"], "I paid 500")
        self.assertEqual(evidence.payload["channel"], "email_confirm")
        self.assertIsNone(self.env["proof.evidence"]._get_chain_error())

    def test_a_message_is_answered_once(self):
        challenge, _mail = self._ask()
        challenge.delivery_ids._answer("confirmed")

        with self.assertRaisesRegex(UserError, "already answered"):
            challenge.delivery_ids._answer("disputed")

    def test_an_answer_we_did_not_ask_for_is_refused(self):
        challenge, _mail = self._ask()

        with self.assertRaisesRegex(UserError, "not one we asked for"):
            challenge.delivery_ids._answer("maybe")

    def test_a_withdrawn_or_expired_request_cannot_be_answered(self):
        withdrawn, _mail = self._ask()
        withdrawn._withdraw()
        expired, _mail = self._ask()

        with self.assertRaisesRegex(UserError, "no longer current"):
            withdrawn.delivery_ids._answer("confirmed")
        with freeze_time(fields.Datetime.now() + timedelta(days=4)):
            with self.assertRaisesRegex(UserError, "no longer current"):
                expired.delivery_ids._answer("confirmed")

    def test_a_contact_without_email_is_not_mailed(self):
        challenge, mails = self._ask(
            partner=self.env["res.partner"].create({"name": "No Mail"})
        )

        self.assertFalse(challenge.delivery_ids)
        self.assertFalse(mails)

    def test_an_unanswered_request_is_reminded_once_then_expires(self):
        challenge, _mail = self._ask()

        with freeze_time(fields.Datetime.now() + timedelta(days=1, hours=1)):
            with self.mock_mail_gateway():
                self.env["proof.challenge"]._cron_follow_up_confirmations()
                self.env["proof.challenge"]._cron_follow_up_confirmations()
                reminders = self._new_mails
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders.subject, "Reminder: please confirm")
        self.assertEqual(challenge.delivery_ids.mapped("state"), ["sent", "sent"])

        with freeze_time(fields.Datetime.now() + timedelta(days=3, hours=1)):
            self.env["proof.challenge"]._cron_follow_up_confirmations()
        self.assertEqual(challenge.state, "expired")
        self.assertEqual(
            challenge.delivery_ids.mapped("state"), ["withdrawn", "withdrawn"]
        )


@tagged("post_install", "-at_install")
class TestEmailConfirmPage(EmailConfirmCase, HttpCase):
    def test_opening_the_link_shows_the_facts_and_answers_nothing(self):
        challenge, mail = self._ask()

        response = self.url_open(self._link(mail))

        self.assertEqual(response.status_code, 200)
        self.assertIn("$ 5,000.00", response.text)
        self.assertIn("Confirm, this is right", response.text)
        self.assertEqual(challenge.state, "issued")

    def test_the_contact_confirms_on_the_page(self):
        challenge, mail = self._ask()
        link = urlparse(self._link(mail))
        page = self.url_open(self._link(mail))
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]

        response = self.url_open(
            f"{link.path}/submit",
            data={
                "csrf_token": csrf,
                "access_token": parse_qs(link.query)["access_token"][0],
                "verdict": "confirmed",
            },
        )

        self.assertIn("You confirmed it", response.text)
        self.assertEqual(
            (challenge.state, challenge.verdict), ("redeemed", "confirmed")
        )
        self.assertEqual(challenge.evidence_id.ip, "127.0.0.1")

    def test_a_link_without_its_token_opens_nothing(self):
        challenge, _mail = self._ask()

        response = self.url_open(f"/proof/answer/{challenge.delivery_ids.id}")

        self.assertEqual(response.status_code, 404)
