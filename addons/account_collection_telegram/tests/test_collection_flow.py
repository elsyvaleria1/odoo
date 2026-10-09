from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .common import CollectionTelegramCase


@tagged("post_install", "-at_install")
class TestCollectionFlow(CollectionTelegramCase):
    def test_a_collector_records_a_cash_collection(self):
        reply = self._collect_cash()

        payment = self._payments()
        self.assertEqual(len(payment), 1, reply)
        self.assertIn(payment.name, reply)
        self.assertEqual(payment.amount, 1000.0)
        self.assertEqual(payment.collection_method, "cash")
        self.assertEqual(payment.journal_id, self.custody_journal)
        self.assertEqual(payment.create_uid, self.collector)
        self.assertTrue(payment.is_in_custody)
        self.assertEqual(self.invoice.amount_residual, 0.0)

    def test_the_customer_gets_the_receipt_on_telegram_and_by_email(self):
        self.customer.email = "sauce@example.com"
        account = self._bound_account("588003", self.customer)
        self.env["telegram.chat"].create(
            {
                "chat_id": "588003",
                "chat_type": "private",
                "bot_id": self.test_bot.id,
                "account_id": account.id,
            }
        )

        reply = self._collect_cash()

        self.assertIn("email, Telegram", reply)
        self.assertIn("/collection/receipt/", reply)

    def test_a_customer_without_email_or_telegram_gets_paper(self):
        reply = self._collect_cash()
        self.assertIn("paper receipt", reply)

    def test_a_check_collection_keeps_its_photo(self):
        self._say("/cobro")
        self._say("Sauce")
        self._press("cob:i:all")
        self._say("400")
        self._press("cob:m:check")
        self.assertIn("written on the check", self._press("cob:d:1"))
        self.assertIn("photo of the check", self._press("cob:k"))
        self.assertIn("photo of the check", self._press("cob:x"))
        self._photo()
        self._say("Skip")
        self._press("cob:ok")

        payment = self._payments()
        self.assertEqual(payment.amount, 400.0)
        self.assertEqual(payment.collection_method, "check")
        self.assertEqual(payment.date, fields.Date.today() - timedelta(days=1))
        self.assertEqual(payment.collection_check_date, payment.date)
        self.assertEqual(self.invoice.amount_residual, 600.0)
        self.assertTrue(payment.message_ids.attachment_ids)

    def test_a_post_dated_check_keeps_the_date_written_on_it(self):
        check_date = fields.Date.today() + timedelta(days=10)
        self._say("/cobro")
        self._say("Sauce")
        self._press("cob:i:all")
        self._say("400")
        self._press("cob:m:check")
        self._press("cob:d:0")
        self._say(check_date.strftime("%d/%m/%Y"))
        self._photo()
        self.assertIn(check_date.strftime("%d/%m/%Y"), self._say("Skip"))
        self._press("cob:ok")

        self.assertEqual(self._payments().collection_check_date, check_date)

    def test_a_collection_records_where_it_was_made(self):
        self.customer.write(
            {"partner_latitude": 19.4326, "partner_longitude": -99.1332}
        )
        self._say("/cobro")
        self._say("Sauce")
        self._press("cob:i:all")
        self._press("cob:a")
        self._press("cob:m:cash")
        self._press("cob:d:0")
        self.assertIn("Share where you are", self._press("cob:x"))
        self.assertIn("shared", self._share_location(19.5, -99.1332))
        self._press("cob:ok")

        payment = self._payments()
        self.assertAlmostEqual(payment.collection_latitude, 19.5)
        self.assertAlmostEqual(payment.collection_distance_km, 7.5, delta=0.1)
        self.assertTrue(payment.is_far_from_customer)

    def test_a_collector_past_due_is_warned_but_still_records(self):
        self._collect_cash()
        self.env["account.payment"].search(
            [("collector_id", "=", self.collector.id)]
        ).date_custody_due = fields.Date.today() - timedelta(days=3)

        reply = self._say("/cobro")

        self.assertIn("past its hand-in date", reply)
        self.assertIn("Who paid you", reply)

    def test_more_than_owed_is_refused(self):
        self._say("/cobro")
        self._say("Sauce")
        self._press("cob:i:all")
        reply = self._say("5000")
        self.assertIn("more than", reply)
        self.assertFalse(self._payments())

    def test_someone_who_is_not_a_collector_is_refused(self):
        reply = self._say("/cobro", chat_id="588002")
        self.assertIn("Only collectors", reply)

    def _speak_for_another_company(self):
        other = self.env["res.company"].create({"name": "TG Collection Bot Co"})
        self.collector.company_ids = [Command.link(other.id)]
        self.test_bot.company_id = other

    def test_a_collection_is_recorded_in_the_bot_s_company(self):
        self._speak_for_another_company()

        reply = self._say("/cobro")

        self.assertIn("no journal for collections in custody", reply)

    def test_custody_lists_only_what_is_held_in_the_bot_s_company(self):
        self._collect_cash()
        self._speak_for_another_company()

        reply = self._say("/custodia")

        self.assertNotIn("Agricola El Sauce", reply)

    def test_custody_lists_what_the_collector_holds(self):
        self._collect_cash()
        reply = self._say("/custodia")
        self.assertIn("Agricola El Sauce", reply)
        self.assertIn("1 collections", reply)

    def test_a_collector_hands_in_to_the_till(self):
        self._collect_cash()
        self._say("/rendir")
        self._press(f"rem:j:{self.till.id}")
        self._press("rem:a")
        self._press("rem:x")
        reply = self._press("rem:ok")

        remittance = self.env["account.collection.remittance"].search(
            [("collector_id", "=", self.collector.id)]
        )
        self.assertEqual(remittance.state, "submitted", reply)
        self.assertEqual(remittance.payment_ids, self._payments())
        self.assertEqual(remittance.destination_journal_id, self.till)
        self.assertIn(remittance.name, reply)

    def test_a_bank_hand_in_gives_a_reference_and_needs_the_slip(self):
        self._collect_cash()
        self._say("/rendir")
        self._press(f"rem:j:{self.bank.id}")
        reply = self._press("rem:a")

        remittance = self.env["account.collection.remittance"].search(
            [("collector_id", "=", self.collector.id)]
        )
        self.assertEqual(remittance.state, "draft")
        self.assertIn(remittance.bank_reference, reply)
        self.assertIn("deposit slip", self._press("rem:x"))
        self._photo()
        self._press("rem:ok")

        self.assertEqual(remittance.state, "submitted")
        self.assertTrue(remittance.message_ids.attachment_ids)

    def test_cancelling_a_bank_hand_in_frees_the_collections(self):
        self._collect_cash()
        self._say("/rendir")
        self._press(f"rem:j:{self.bank.id}")
        self._press("rem:a")
        self._say("/cancelar")

        remittance = self.env["account.collection.remittance"].search(
            [("collector_id", "=", self.collector.id)]
        )
        self.assertEqual(remittance.state, "cancel")
        self.assertFalse(self._payments().collection_remittance_id)

    def test_an_abandoned_hand_in_is_cancelled_on_the_next_one(self):
        self._collect_cash()
        self._say("/rendir")
        self._press(f"rem:j:{self.bank.id}")
        self._press("rem:a")
        self.test_chat.search([("chat_id", "=", "588001")])._flow_end()

        reply = self._say("/rendir")

        self.assertIn("unfinished hand-in", reply)
        self.assertIn("Where did the money go", reply)
