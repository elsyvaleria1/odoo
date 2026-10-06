from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCollectedCheck(CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fee_account = cls.env["account.account"].create(
            {"name": "Bounced check fees", "code": "703997", "account_type": "income"}
        )
        cls.env.company.account_config_id.collection_check_fee_account_id = (
            cls.fee_account
        )

    def _remit(self, payments, journal, **vals):
        remittance = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create({"destination_journal_id": journal.id, **vals})
        )
        remittance.payment_ids = payments
        remittance.action_submit()
        return remittance.with_env(self.env)

    def _deposited_check(self, amount=1000.0):
        invoice = self._post_invoice(amount)
        payment = self._collect(invoice, amount, method="check").with_env(self.env)
        remittance = self._remit(payment, self.bank_journal)
        remittance.with_user(self.treasurer).action_validate()
        return invoice, payment, remittance

    def test_a_check_is_followed_from_custody_to_the_bank(self):
        invoice = self._post_invoice(1000.0)
        payment = self._collect(invoice, 1000.0, method="check")
        self.assertEqual(payment.collection_check_state, "custody")

        remittance = self._remit(payment, self.bank_journal)
        remittance.with_user(self.treasurer).action_validate()
        self.assertEqual(payment.collection_check_state, "deposited")

        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "amount": 1000.0,
                "payment_ref": "check deposit",
                "date": self.today,
            }
        )
        remittance.statement_line_id = st_line
        self.assertEqual(payment.collection_check_state, "cleared")

    def test_a_cash_collection_has_no_check_status(self):
        payment = self._collect(self._post_invoice(100.0), 100.0)
        self.assertFalse(payment.collection_check_state)

    def test_a_post_dated_check_waits_for_its_date(self):
        check_date = self.today + timedelta(days=5)
        payment = self._collect(
            self._post_invoice(1000.0), 1000.0, method="check", check_date=check_date
        )
        self.assertEqual(payment.collection_check_date, check_date)

        early = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create({"destination_journal_id": self.bank_journal.id})
        )
        early.action_load_custody()
        self.assertFalse(early.payment_ids)
        early.payment_ids = payment
        with self.assertRaisesRegex(UserError, "dated after"):
            early.action_submit()

        on_time = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create(
                {"destination_journal_id": self.bank_journal.id, "date": check_date}
            )
        )
        early.action_cancel()
        on_time.action_load_custody()
        self.assertEqual(on_time.payment_ids, payment)

    def test_a_bounced_check_opens_its_invoice_again(self):
        invoice, payment, remittance = self._deposited_check()
        self.assertEqual(invoice.payment_state, "paid")

        wizard = Form(
            self.env["wizard.account.payment.bounce"]
            .with_user(self.treasurer)
            .with_context(default_payment_id=payment.id)
        )
        wizard.reason = "Insufficient funds"
        wizard.fee = 150.0
        wizard.save().action_bounce()

        self.assertEqual(payment.state, "rejected")
        self.assertEqual(payment.collection_check_state, "bounced")
        self.assertEqual(invoice.payment_state, "not_paid")
        bounce = payment.collection_bounce_move_id
        self.assertEqual(bounce.state, "posted")
        self.assertEqual(bounce.journal_id, self.bank_journal)
        fee_line = bounce.line_ids.filtered(
            lambda line: line.account_id == self.fee_account
        )
        self.assertEqual(fee_line.balance, -150.0)
        transfer = self.env.company.account_config_id.transfer_account_id
        self.assertEqual(
            bounce.line_ids.filtered(lambda line: line.account_id == transfer).balance,
            -1000.0,
        )
        open_on_customer = self.env["account.move.line"].search(
            [
                ("partner_id", "=", invoice.commercial_partner_id.id),
                (
                    "account_id",
                    "=",
                    invoice.line_ids.account_id.filtered(
                        lambda account: account.account_type == "asset_receivable"
                    ).id,
                ),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
            ]
        )
        self.assertEqual(sum(open_on_customer.mapped("amount_residual")), 1150.0)
        self.assertEqual(payment.activity_ids.user_id, self.collector)
        with self.assertRaisesRegex(UserError, "bounced"):
            remittance.action_revert()

    def test_a_check_still_in_custody_cannot_bounce(self):
        payment = self._collect(self._post_invoice(100.0), 100.0, method="check")
        with self.assertRaises(UserError):
            payment._bounce_collection_check(self.today, 0.0, "returned")
