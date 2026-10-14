from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPurchaseTaxPolicy(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_a.supplier_taxes_id = cls.tax_purchase_a
        expense = cls.company_data["default_account_expense"]
        cls.forbidden_journal = cls.env["account.journal"].create(
            {
                "name": "Bills Without Taxes",
                "code": "POTF",
                "type": "purchase",
                "sequence": 100,
                "default_account_id": expense.id,
                "tax_policy": "forbidden",
            }
        )
        cls.required_journal = cls.env["account.journal"].create(
            {
                "name": "Bills With Taxes",
                "code": "POTR",
                "type": "purchase",
                "sequence": 101,
                "default_account_id": expense.id,
                "tax_policy": "required",
            }
        )

    def _order(self, journal, line_vals=None):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "journal_id": journal.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1.0,
                            **(line_vals or {}),
                        }
                    )
                ],
            }
        )

    def test_forbidden_journal_never_fetches_product_taxes(self):
        order = self._order(self.forbidden_journal)
        self.assertFalse(order.line_ids.tax_ids)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_journal_switch_drops_and_restores_automatic_taxes(self):
        order = self._order(self.required_journal)
        self.assertEqual(order.line_ids.tax_ids, self.tax_purchase_a)
        order.journal_id = self.forbidden_journal
        self.assertFalse(order.line_ids.tax_ids)
        order.journal_id = self.required_journal
        self.assertEqual(order.line_ids.tax_ids, self.tax_purchase_a)

    def test_manual_tax_on_forbidden_journal_blocks_confirmation(self):
        order = self._order(
            self.forbidden_journal,
            line_vals={"tax_ids": [Command.set(self.tax_purchase_b.ids)]},
        )
        with self.assertRaisesRegex(UserError, "forbids taxes"):
            order.action_confirm()

    def test_required_journal_blocks_an_untaxed_line(self):
        order = self._order(
            self.required_journal, line_vals={"tax_ids": [Command.clear()]}
        )
        with self.assertRaisesRegex(UserError, "requires a tax"):
            order.action_confirm()
