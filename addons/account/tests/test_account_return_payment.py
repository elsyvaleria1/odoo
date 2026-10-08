from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestAccountReturnPayment(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data["company"].write(
            {
                "vat": "US12345671",
                "phone_ids": [
                    Command.create({"number": "123456789", "type": "landline"})
                ],
                "email": "test@gmail.com",
            }
        )
        cls.authority = cls.env["res.partner"].create({"name": "Tax Authority"})
        cls.settlement_account = cls.env["account.account"].create(
            {
                "name": "Taxes due to the authority",
                "code": "test.tax.settlement",
                "account_type": "liability_payable",
                "reconcile": True,
            }
        )
        tax_account, payable_account, receivable_account = cls.env[
            "account.account"
        ].create(
            [
                {
                    "name": f"Test {name}",
                    "code": f"test.tax.{name}",
                    "account_type": account_type,
                }
                for name, account_type in (
                    ("collected", "liability_current"),
                    ("payable", "liability_current"),
                    ("receivable", "asset_current"),
                )
            ]
        )
        cls.tax_payable_account = payable_account
        tax_group = cls.env["account.tax.group"].create(
            {
                "name": "Test VAT",
                "tax_payable_account_id": payable_account.id,
                "tax_receivable_account_id": receivable_account.id,
            }
        )
        cls.sale_tax = cls.env["account.tax"].create(
            {
                "name": "sale tax 21",
                "amount": 21,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "tax_group_id": tax_group.id,
                "company_ids": [Command.set(cls.env.company.ids)],
                "invoice_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create(
                        {"repartition_type": "tax", "account_id": tax_account.id}
                    ),
                ],
                "refund_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create(
                        {"repartition_type": "tax", "account_id": tax_account.id}
                    ),
                ],
            }
        )
        cls.return_type = cls.env["account.return.type"].create(
            {
                "category": "account_return",
                "default_deadline_periodicity": "monthly",
                "default_deadline_start_date": "2024-01-01",
                "name": "Settled VAT",
                "report_id": cls.env.ref("account.generic_tax_report").id,
                "states_workflow": "generic_state_tax_report",
                "payment_partner_id": cls.authority.id,
            }
        )
        cls.return_type.settlement_account_id = cls.settlement_account
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _submitted_return(self, return_type=None):
        tax_return = (
            (return_type or self.return_type)
            .with_context(
                forced_date_from=fields.Date.from_string("2024-02-01"),
                forced_date_to=fields.Date.from_string("2024-02-29"),
            )
            ._try_create_returns_for_fiscal_year(self.env.company, False)
        )
        self.init_invoice(
            "out_invoice",
            amounts=[1000],
            invoice_date="2024-02-10",
            taxes=[self.sale_tax],
            post=True,
        )
        with patch.object(
            self.registry["account.return"],
            "_generate_locking_attachments",
            lambda self, options: None,
        ):
            tax_return.action_validate()
        wizard_action = tax_return.action_submit()
        self.assertEqual(tax_return.state, "submitted")
        wizard = self.env[wizard_action["res_model"]].browse(wizard_action["res_id"])
        return tax_return, wizard

    def _pay_from_bank(self, lines, amount, user=None):
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "payment_ref": "VAT February",
                "amount": amount,
                "date": "2024-03-15",
            }
        )
        st_line.with_user(user or self.env.user).set_line_bank_statement_line(lines.ids)
        return st_line

    def test_the_closing_moves_the_amount_due_onto_one_settlement_line(self):
        tax_return, _wizard = self._submitted_return()

        settlement = tax_return._get_settlement_lines()
        self.assertRecordValues(
            settlement,
            [
                {
                    "account_id": self.settlement_account.id,
                    "partner_id": self.authority.id,
                    "balance": -210.0,
                }
            ],
        )
        self.assertFalse(
            tax_return.closing_move_ids.line_ids.filtered(
                lambda line: line.account_id == self.tax_payable_account
            )
        )
        self.assertEqual(tax_return.total_amount_to_pay, 210.0)

    def test_the_return_is_paid_once_the_bank_confirms_the_payment(self):
        tax_return, wizard = self._submitted_return()
        wizard.journal_id = self.bank_journal
        wizard.action_create_payment()

        return_payment = tax_return.payment_ids
        self.assertRecordValues(
            return_payment,
            [{"state": "in_process", "amount": 210.0, "partner_id": self.authority.id}],
        )
        self.assertTrue(tax_return._get_settlement_lines().reconciled)
        self.assertEqual(tax_return.state, "submitted")

        liquidity, _counterpart, _writeoff = return_payment.payment_id._seek_for_lines()
        self._pay_from_bank(liquidity, -210.0)

        self.assertEqual(return_payment.state, "paid")
        self.assertEqual(tax_return.state, "paid")
        self.assertTrue(tax_return.is_completed)

    def test_a_bank_line_settling_the_closing_directly_pays_the_return(self):
        tax_return, _wizard = self._submitted_return()

        self._pay_from_bank(tax_return._get_settlement_lines(), -210.0)

        self.assertEqual(tax_return.state, "paid")
        self.assertTrue(tax_return.is_completed)

    def test_a_billing_user_reconciling_the_bank_settles_the_return(self):
        tax_return, _wizard = self._submitted_return()
        billing_user = new_test_user(
            self.env,
            login="billing_settles_vat",
            groups="account.group_account_invoice",
            company_id=self.env.company.id,
            company_ids=self.env.company.ids,
        )
        self.assertFalse(
            tax_return.with_user(billing_user).has_access("write"),
            "the test needs a user who cannot write returns",
        )

        self._pay_from_bank(
            tax_return._get_settlement_lines(), -210.0, user=billing_user
        )

        self.assertEqual(tax_return.state, "paid")

    def test_unreconciling_the_settlement_reopens_the_return(self):
        tax_return, _wizard = self._submitted_return()
        self._pay_from_bank(tax_return._get_settlement_lines(), -210.0)
        self.assertEqual(tax_return.state, "paid")

        tax_return._get_settlement_lines().remove_move_reconcile()

        self.assertEqual(tax_return.state, "submitted")
        self.assertFalse(tax_return.is_completed)

    def test_a_partial_bank_payment_leaves_the_return_unpaid(self):
        tax_return, _wizard = self._submitted_return()

        self._pay_from_bank(tax_return._get_settlement_lines(), -100.0)

        self.assertEqual(tax_return.state, "submitted")

    def test_a_settled_return_cannot_be_marked_paid_by_hand(self):
        _tax_return, wizard = self._submitted_return()

        with self.assertRaises(UserError):
            wizard.action_mark_as_paid()

    def test_sending_payment_instructions_does_not_mark_the_return_paid(self):
        unsettled_type = self.return_type.copy({"name": "Unsettled VAT"})
        unsettled_type.settlement_account_id = False
        tax_return, wizard = self._submitted_return(unsettled_type)
        self.assertFalse(wizard.has_settlement)

        compose_action = wizard.action_send_email_instructions()
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(compose_action["context"])
            .create({})
        )
        composer.action_send_mail()

        self.assertEqual(tax_return.state, "submitted")
        self.assertRecordValues(tax_return.payment_ids, [{"state": "instructed"}])

        wizard.action_mark_as_paid()
        self.assertEqual(tax_return.state, "paid")
