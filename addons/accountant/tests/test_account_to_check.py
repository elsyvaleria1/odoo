from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools.authority_keys import strip_authority_keys

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCheckAccountMoves(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simple_accountman.group_ids = cls.env.ref("account.group_account_invoice")
        cls.bank_journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1
        )

    def test_a_client_cannot_send_the_review_skip_key(self):
        self.assertEqual(
            strip_authority_keys({"skip_account_review_check": True, "lang": "en_US"}),
            {"lang": "en_US"},
        )

    def test_try_check_move_with_invoicing_user(self):
        invoice = self._create_invoice(checked=True)
        invoice.action_post()
        with self.assertRaisesRegex(
            ValidationError, "Validated entries can only be changed by your accountant."
        ):
            invoice.with_user(self.simple_accountman).action_draft()

        invoice.action_draft()
        self.assertEqual(invoice.state, "draft")

        invoice.action_post()
        invoice.checked = False
        invoice.with_user(self.simple_accountman).action_draft()
        self.assertEqual(invoice.state, "draft")

    def test_post_move_auto_check(self):
        invoice_admin = self._create_invoice()
        invoice_admin.action_post()
        self.assertTrue(invoice_admin.checked)

        invoice_invoicing = self._create_invoice(user_id=self.simple_accountman.id)
        invoice_invoicing.with_user(self.simple_accountman).action_post()
        self.assertFalse(invoice_invoicing.checked)

    def test_post_move_auto_check_with_auto_post(self):
        invoice = self._create_invoice(auto_post="at_date", date=fields.Date.today())
        self.assertFalse(invoice.checked)
        with (
            freeze_time(invoice.date + relativedelta(days=1)),
            self.sync_env_with_side_cursors(),
        ):
            self.env.ref(
                "account.ir_cron_auto_post_draft_entry"
            ).method_direct_trigger()
        self.assertTrue(invoice.checked)

    def test_create_statement_line_auto_check(self):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "payment_method_id": self.env.ref(
                    "account.account_payment_method_manual_in"
                ).id,
                "partner_type": "customer",
                "amount": 100,
                "journal_id": self.company_data["default_journal_bank"].id,
                "memo": "INV/2025/00001",
            }
        )
        payment.action_post()

        bank_line_1 = self.env["account.bank.statement.line"].create(
            [
                {
                    "journal_id": self.bank_journal.id,
                    "date": "2025-01-01",
                    "payment_ref": "INV/2025/00001",
                    "amount": -100,
                }
            ]
        )
        bank_line_1._try_auto_reconcile_statement_lines()
        self.assertTrue(bank_line_1.move_id.checked)
        with self.assertRaisesRegex(
            ValidationError, "Validated entries can only be changed by your accountant."
        ):
            bank_line_1.with_user(self.simple_accountman).remove_reconciled_line(
                payment.move_id.line_ids[0].id
            )

    def test_a_paid_invoice_reaches_in_payment_not_paid(self):
        """`_get_invoice_in_payment_state` is what turns the `in_payment` state on
        for this edition, and nothing in this module asserted it. Without the
        override the same invoice would go straight to `paid`, and only core's
        tests -- which branch on the returned value rather than requiring it --
        would notice.
        """
        invoice = self._create_invoice(post=True)
        self.assertEqual(invoice.payment_state, "not_paid")

        self.env["wizard.account.move.line.pay"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({})._create_payments()

        self.assertEqual(
            invoice.payment_state,
            "in_payment",
            "the outstanding account keeps a paid invoice in `in_payment` until"
            " the payment is reconciled with a bank statement",
        )
        self.assertEqual(invoice._get_invoice_in_payment_state(), "in_payment")
