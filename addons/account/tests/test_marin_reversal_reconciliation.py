from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestReversalReconciliation(AccountTestInvoicingCommon):
    def _refund(self, invoice, amount):
        refund = invoice._reverse_moves()
        refund.invoice_line_ids.write({"price_unit": amount})
        return refund

    def _reconciliation_by_refund(self, refunds):
        result = {}
        for refund in refunds:
            lines = refund.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            )
            result[refund.name] = (
                all(lines.mapped("reconciled")),
                lines.matched_debit_ids.debit_move_id.move_id.mapped("name"),
            )
        return result

    def test_two_refunds_of_one_invoice_posted_together_are_both_reconciled_with_it(
        self,
    ):
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], post=True)
        first = self._refund(invoice, 100.0)
        second = self._refund(invoice, 200.0)

        (first | second).action_post()

        self.assertEqual(
            self._reconciliation_by_refund(first | second),
            {
                first.name: (True, [invoice.name]),
                second.name: (True, [invoice.name]),
            },
        )

    def test_refunds_of_two_invoices_posted_together_each_reconcile_with_their_own(
        self,
    ):
        invoice_a = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[1000.0], post=True
        )
        invoice_b = self.init_invoice(
            "out_invoice", partner=self.partner_b, amounts=[1000.0], post=True
        )
        refund_a1 = self._refund(invoice_a, 100.0)
        refund_a2 = self._refund(invoice_a, 200.0)
        refund_b = self._refund(invoice_b, 300.0)
        refunds = refund_a1 | refund_a2 | refund_b

        refunds.action_post()

        self.assertEqual(
            self._reconciliation_by_refund(refunds),
            {
                refund_a1.name: (True, [invoice_a.name]),
                refund_a2.name: (True, [invoice_a.name]),
                refund_b.name: (True, [invoice_b.name]),
            },
        )

    def test_a_cash_basis_refund_does_not_reconcile_transition_lines_twice(self):
        self.env.company.account_config_id.tax_exigibility = True
        transition_account = self.env["account.account"].create(
            {
                "code": "209990",
                "name": "Cash basis transition",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        tax = self.env["account.tax"].create(
            {
                "name": "cash basis 10%",
                "amount": 10.0,
                "tax_exigibility": "on_payment",
                "cash_basis_transition_account_id": transition_account.id,
            }
        )
        invoice = self.init_invoice(
            "out_invoice", amounts=[1000.0], taxes=tax, post=True
        )
        refund = invoice._reverse_moves()

        refund.action_post()

        receivable_lines = (invoice + refund).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        self.assertTrue(all(receivable_lines.mapped("reconciled")))
        self.assertEqual(
            receivable_lines.full_reconcile_id.reconciled_line_ids, receivable_lines
        )
        for move in invoice + refund:
            transition_line = move.line_ids.filtered(
                lambda line: line.account_id == transition_account
            )
            self.assertTrue(transition_line.reconciled)
            self.assertEqual(
                (
                    transition_line.matched_debit_ids.debit_move_id
                    | transition_line.matched_credit_ids.credit_move_id
                ).move_id.tax_cash_basis_origin_move_id,
                move,
            )
