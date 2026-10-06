from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestBankStatementAutoReconcileRule(TestBankRecWidgetCommon):
    def _invoice(self, amount, **kwargs):
        return self._create_invoice_line(
            "out_invoice",
            invoice_line_ids=[
                {
                    "price_unit": amount,
                    "account_id": self.company_data["default_account_revenue"].id,
                }
            ],
            **kwargs,
        )

    def test_a_match_by_partner_and_amount_is_recorded(self):
        self._invoice(321.0)
        st_line = self._create_st_line(321.0, partner_id=self.partner_a.id)

        st_line._try_auto_reconcile_statement_lines()

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(st_line.auto_reconcile_rule, "amount")

    def test_a_match_by_reference_is_recorded(self):
        self._invoice(321.0, ref="REFERENCEAAA")
        self._invoice(321.0, ref="REFERENCEBBB")
        st_line = self._create_st_line(
            321.0, payment_ref="PAYMENT REFERENCEBBB", partner_id=self.partner_a.id
        )

        st_line._try_auto_reconcile_statement_lines()

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(st_line.auto_reconcile_rule, "reference")

    def test_a_match_by_an_automated_model_is_recorded(self):
        st_line = self._create_st_line(-12.0, payment_ref="MONTHLY ACCOUNT FEE")
        self._create_reconcile_model(
            trigger="auto_reconcile",
            match_label="contains",
            match_label_param="ACCOUNT FEE",
            line_ids=[{}],
        )
        self.assertTrue(
            st_line.is_reconciled,
            "writing an automated model applies it to the open transactions",
        )
        other = self._create_st_line(-13.0, payment_ref="MONTHLY ACCOUNT FEE")

        other._try_auto_reconcile_statement_lines()

        self.assertTrue(other.is_reconciled)
        self.assertEqual(other.auto_reconcile_rule, "model")

    def test_a_match_made_by_a_person_carries_no_rule(self):
        invoice = self._invoice(321.0)
        st_line = self._create_st_line(321.0)

        st_line.set_line_bank_statement_line(invoice.ids)

        self.assertTrue(st_line.is_reconciled)
        self.assertFalse(st_line.auto_reconcile_rule)

    def test_a_partial_match_carries_no_rule(self):
        self._invoice(100.0, ref="PARTIALREFAAA")
        st_line = self._create_st_line(
            321.0, payment_ref="PAYMENT PARTIALREFAAA", partner_id=self.partner_a.id
        )

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(
            st_line.auto_reconcile_rule,
            "the rule left a remainder for a person to settle",
        )

    def test_undoing_an_automatic_match_forgets_its_rule(self):
        self._invoice(321.0)
        st_line = self._create_st_line(321.0, partner_id=self.partner_a.id)
        st_line._try_auto_reconcile_statement_lines()
        self.assertEqual(st_line.auto_reconcile_rule, "amount")

        st_line.action_undo_reconciliation()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(st_line.auto_reconcile_rule)

    def test_removing_a_matched_line_forgets_the_rule(self):
        self._invoice(321.0)
        st_line = self._create_st_line(321.0, partner_id=self.partner_a.id)
        st_line._try_auto_reconcile_statement_lines()
        _liquidity, _suspense, matched = st_line._seek_for_lines()

        st_line.remove_reconciled_line(matched.ids)

        self.assertFalse(st_line.auto_reconcile_rule)
