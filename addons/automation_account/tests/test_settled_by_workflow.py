from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestSettledByWorkflow(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner.id,
                "journal_id": cls.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Collected by a workflow",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": cls.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        cls.invoice.action_post()

    def setUp(self):
        super().setUp()
        self._make_step("pass")
        self.st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "date": "2026-08-21",
                "payment_ref": "SPEI RECIBIDO",
                "partner_id": self.partner.id,
                "amount": 100.0,
            },
        )

    def test_the_automatic_matching_leaves_a_line_with_a_live_workflow_alone(self):
        self._make_runtime(st_line_id=self.st_line.id)

        self.st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(self.st_line.is_reconciled)
        self.assertEqual(self.invoice.payment_state, "not_paid")

    def test_a_cancelled_workflow_hands_the_line_back_to_the_matching(self):
        self._make_runtime(st_line_id=self.st_line.id).action_cancel()

        self.st_line._try_auto_reconcile_statement_lines()

        self.assertTrue(self.st_line.is_reconciled)
