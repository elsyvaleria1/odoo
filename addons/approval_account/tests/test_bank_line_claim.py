from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestBankLineClaim(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Collection with bank line",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
                "has_bsl": "required",
            }
        )
        add_category_approver(cls.category, cls.approver, required=True)

    def _line(self, amount=1234.56, date="2026-06-01", **vals):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": date,
                "amount": amount,
                "payment_ref": "SPEI RECIBIDO",
                **vals,
            }
        )

    def _submitted(self, amount=1234.56, date="2026-06-01"):
        request = self.env["approval.request"].create(
            {
                "name": "Collection",
                "category_id": self.category.id,
                "partner_id": self.partner_a.id,
                "amount": amount,
                "date": date,
            }
        )
        request.action_confirm()
        return request

    def test_a_submitted_request_takes_the_one_transaction_it_fits(self):
        line = self._line()

        request = self._submitted()

        self.assertEqual(request.bank_statement_line_id, line)
        self.assertIn("assigned automatically", request.message_ids[:1].body)

    def test_a_transaction_arriving_later_is_taken_by_the_request_waiting_for_it(self):
        request = self._submitted()
        self.assertFalse(request.bank_statement_line_id)

        line = self._line()

        self.assertEqual(request.bank_statement_line_id, line)

    def test_a_request_fitting_two_transactions_is_left_to_a_person(self):
        self._line()
        self._line()

        request = self._submitted()

        self.assertFalse(request.bank_statement_line_id)

    def test_a_transaction_two_requests_fit_is_left_to_a_person(self):
        first = self._submitted()
        second = self._submitted()

        self._line()

        self.assertFalse(first.bank_statement_line_id)
        self.assertFalse(second.bank_statement_line_id)

    def test_a_transaction_before_the_request_date_is_not_offered(self):
        self._line(date="2026-05-31")

        request = self._submitted()

        self.assertFalse(request.bank_statement_line_id)

    def test_an_outgoing_transaction_of_the_amount_fits_as_well(self):
        line = self._line(amount=-1234.56)

        request = self._submitted()

        self.assertEqual(request.bank_statement_line_id, line)

    def test_a_draft_request_takes_nothing(self):
        self._line()
        request = self.env["approval.request"].create(
            {
                "name": "Draft collection",
                "category_id": self.category.id,
                "partner_id": self.partner_a.id,
                "amount": 1234.56,
                "date": "2026-06-01",
            }
        )

        self.assertFalse(request.bank_statement_line_id)

    def test_the_automatic_matching_leaves_a_claimed_transaction_alone(self):
        invoice = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[1234.56], post=True
        )
        line = self._line(partner_id=self.partner_a.id)
        request = self._submitted()
        self.assertEqual(request.bank_statement_line_id, line)

        line._try_auto_reconcile_statement_lines()

        self.assertFalse(line.is_reconciled)
        self.assertEqual(invoice.payment_state, "not_paid")

    def test_an_importer_without_rights_on_approvals_still_triggers_the_claim(self):
        request = self._submitted()
        accountant = new_test_user(
            self.env,
            login="claim_accountant",
            groups="account.group_account_user",
            company_id=self.env.company.id,
        )

        line = (
            self.env["account.bank.statement.line"]
            .with_user(accountant)
            .create(
                {
                    "journal_id": self.bank_journal.id,
                    "date": "2026-06-01",
                    "amount": 1234.56,
                    "payment_ref": "SPEI RECIBIDO",
                }
            )
        )

        self.assertEqual(request.bank_statement_line_id, line)

    def test_a_requester_without_accounting_rights_still_gets_the_transaction(self):
        line = self._line()
        requester = new_test_user(
            self.env,
            login="claim_requester",
            groups="base.group_user",
            company_id=self.env.company.id,
        )

        request = (
            self.env["approval.request"]
            .with_user(requester)
            .create(
                {
                    "name": "Collection",
                    "category_id": self.category.id,
                    "partner_id": self.partner_a.id,
                    "amount": 1234.56,
                    "date": "2026-06-01",
                }
            )
        )
        request.action_confirm()

        self.assertEqual(request.with_env(self.env).bank_statement_line_id, line)
