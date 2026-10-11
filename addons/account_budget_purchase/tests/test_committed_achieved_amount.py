from odoo import Command
from odoo.tests import tagged

from .common import TestAccountBudgetPurchaseCommon


@tagged("post_install", "-at_install")
class TestCommittedAchievedAmount(TestAccountBudgetPurchaseCommon):
    def create_other_category_aal(self):
        self.env["account.analytic.line"].create(
            {
                "name": "aal 1",
                "date": "2019-01-10",
                self.project_column_name: self.analytic_account_partner_a.id,
                "amount": 200,
            }
        )
        self.env["account.analytic.line"].create(
            {
                "name": "aal 2",
                "date": "2019-01-10",
                self.project_column_name: self.analytic_account_partner_b.id,
                "amount": 200,
            }
        )
        self.env["account.analytic.line"].create(
            {
                "name": "aal 3",
                "date": "2019-01-10",
                self.project_column_name: self.analytic_account_partner_a.id,
                "amount": -100,
            }
        )
        self.env["account.analytic.line"].create(
            {
                "name": "aal 4",
                "date": "2019-01-10",
                self.project_column_name: self.analytic_account_partner_b.id,
                "amount": -100,
            }
        )

    def test_budget_revenue_committed_achieved_amount(self):
        plan_a_line, plan_b_line, plan_b_admin_line = (
            self.budget_analytic_revenue.budget_line_ids
        )
        self.assertEqual(plan_a_line.achieved_amount, 0)
        self.assertEqual(plan_b_line.achieved_amount, 0)
        self.assertEqual(plan_b_admin_line.achieved_amount, 0)
        bill = self.purchase_order.invoice_ids

        (bill + self.out_invoice).action_post()

        self.env["purchase.order"].invalidate_model(["currency_rate"])
        self.env["purchase.order.line"].invalidate_model(
            ["qty_transferred", "qty_invoiced", "price_unit"]
        )
        self.env["budget.line"].invalidate_model(
            ["achieved_amount", "committed_amount"]
        )
        self.create_other_category_aal()

        self.assertEqual(plan_a_line.achieved_amount, 800.0)
        self.assertEqual(plan_a_line.committed_amount, 800.0)

        self.assertEqual(plan_b_line.achieved_amount, 1500.0)
        self.assertEqual(plan_b_line.committed_amount, 1500.0)

        self.assertEqual(plan_b_admin_line.achieved_amount, 600.0)
        self.assertEqual(plan_b_admin_line.committed_amount, 600.0)

    def test_budget_analytic_expense_committed_achieved_amount(self):
        plan_a_line, plan_b_line, plan_b_admin_line = (
            self.budget_analytic_expense.budget_line_ids
        )
        self.assertEqual(plan_a_line.achieved_amount, 0)
        self.assertEqual(plan_b_line.achieved_amount, 0)
        self.assertEqual(plan_b_admin_line.achieved_amount, 0)
        bill = self.purchase_order.invoice_ids
        bill.write({"invoice_date": "2019-01-10"})
        bill.action_post()

        self.env["purchase.order"].invalidate_model(["currency_rate"])
        self.env["purchase.order.line"].invalidate_model(
            ["qty_transferred", "qty_invoiced", "price_unit"]
        )
        self.env["budget.line"].invalidate_model(
            ["achieved_amount", "committed_amount"]
        )
        self.create_other_category_aal()

        self.assertEqual(plan_a_line.achieved_amount, 500.0)

        self.assertEqual(plan_a_line.committed_amount, 2100.0)

        self.assertEqual(plan_b_line.achieved_amount, 1200.0)

        self.assertEqual(plan_b_line.committed_amount, 2100.0)

        self.assertEqual(plan_b_admin_line.achieved_amount, 500.0)

        self.assertEqual(plan_b_admin_line.committed_amount, 1000.0)

        no_po_bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-11",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                            "quantity": 3,
                            "price_unit": 100,
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                        }
                    ),
                ],
            }
        )
        no_po_bill.action_post()
        self.env["budget.line"].invalidate_model(
            ["achieved_amount", "committed_amount"]
        )
        self.assertEqual(plan_a_line.achieved_amount, 800.0)
        self.assertEqual(plan_a_line.committed_amount, 2400.0)

    def test_budget_analytic_expense_committed_amount_draft_bill(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        purchase_order.line_ids.qty_transferred = 1

        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=100, achieved=0)

        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_date = "2019-01-10"
        self.assertBudgetLine(plan_a_line, committed=100, achieved=0)

        purchase_order.invoice_ids.action_post()
        self.assertBudgetLine(plan_a_line, committed=100, achieved=100)

    def test_budget_analytic_discount_and_included_tax_amounts(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        self.tax_purchase_a.price_include = True
        self.tax_purchase_a.amount_type = "division"
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 2,
                            "discount": 10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                            "tax_ids": self.tax_purchase_a.ids,
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        purchase_order.line_ids.qty_transferred = 2

        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=153, achieved=0)

        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_date = "2019-01-10"
        self.assertBudgetLine(plan_a_line, committed=153, achieved=0)

        purchase_order.invoice_ids.action_post()
        self.assertBudgetLine(plan_a_line, committed=153, achieved=153)

    def test_budget_multi_currency(self):
        currency = self.setup_other_currency("EUR")
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "currency_id": currency.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        self.assertRecordValues(
            purchase_order,
            [
                {
                    "currency_rate": 2,
                    "amount_total": 2000,
                }
            ],
        )

        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=0)

        purchase_order.line_ids.qty_transferred = 2
        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        self.assertRecordValues(
            bill,
            [
                {
                    "currency_id": currency.id,
                    "amount_total": 400,
                    "amount_total_signed": -200,
                }
            ],
        )
        bill.invoice_date = "2019-01-10"
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=200)

    def test_budget_analytic_multiple_bills_from_po(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=0)

        purchase_order.line_ids.qty_transferred = 5
        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_date = "2019-01-10"
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=0)
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=500)

        purchase_order.line_ids.qty_transferred = 7
        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_date = "2019-01-10"
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=1000, achieved=700)

    def test_multiple_bills_from_po_multiple_uom(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        gravel_ton = self.env["product.product"].create(
            {
                "name": "Gravel 1T",
                "uom_id": self.env.ref("base.product_uom_ton").id,
                "standard_price": 1000,
            }
        )
        gravel_kilo = self.env["product.product"].create(
            {
                "name": "Gravel 1kg",
                "uom_id": self.env.ref("base.product_uom_kgm").id,
                "standard_price": 1,
            }
        )
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": gravel_ton.id,
                            "product_qty": 3.5,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=3500, achieved=0)

        purchase_order.line_ids.qty_transferred = 2
        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_date = "2019-01-10"
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=3500, achieved=2000)

        purchase_order.line_ids.qty_transferred = 3.5
        bill = self.env["account.move"].browse(purchase_order.create_invoice().id)
        bill.invoice_line_ids.write(
            {
                "product_id": gravel_kilo.id,
                "quantity": 1500,
            }
        )
        bill.invoice_date = "2019-01-10"
        self.assertBudgetLine(plan_a_line, committed=3500, achieved=2000)
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=3500, achieved=3500)

    def test_budget_analytic_both_committed_achieved_amount(self):
        plan_a_line, plan_b_line, plan_b_admin_line = (
            self.budget_analytic_both.budget_line_ids
        )
        self.assertEqual(plan_a_line.achieved_amount, 0)
        self.assertEqual(plan_b_line.achieved_amount, 0)
        self.assertEqual(plan_b_admin_line.achieved_amount, 0)
        bill = self.purchase_order.invoice_ids
        bill.write({"invoice_date": "2019-01-10"})

        (bill + self.out_invoice).action_post()

        self.env["purchase.order"].invalidate_model(["currency_rate"])
        self.env["purchase.order.line"].invalidate_model(
            ["qty_transferred", "qty_invoiced", "price_unit"]
        )
        self.env["budget.line"].invalidate_model(
            ["achieved_amount", "committed_amount"]
        )
        self.create_other_category_aal()

        self.assertEqual(plan_a_line.achieved_amount, 300)

        self.assertEqual(plan_a_line.committed_amount, -1300)

        self.assertEqual(plan_b_line.achieved_amount, 300)

        self.assertEqual(plan_b_line.committed_amount, -600)

        self.assertEqual(plan_b_admin_line.achieved_amount, 100)

        self.assertEqual(plan_b_admin_line.committed_amount, -400)

    def test_budget_analytic_misc_entry(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        journal_entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-10",
                "date": "2019-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner_a.id,
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                            "debit": 100,
                        }
                    ),
                    Command.create(
                        {
                            "partner_id": self.partner_a.id,
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                            "credit": 70,
                        }
                    ),
                    Command.create(
                        {
                            "partner_id": self.partner_a.id,
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "credit": 30,
                        }
                    ),
                ],
            }
        )
        journal_entry.action_post()

        budget_both_line_a = self.budget_analytic_both.budget_line_ids[0]
        self.assertEqual(
            (budget_both_line_a.committed_amount, budget_both_line_a.achieved_amount),
            (-30, -30),
        )

        budget_expense_line_a = self.budget_analytic_expense.budget_line_ids[0]
        self.assertEqual(
            (
                budget_expense_line_a.committed_amount,
                budget_expense_line_a.achieved_amount,
            ),
            (30, 30),
        )

    def test_budget_analytic_expense_with_credit_note(self):
        plan_a_line, plan_b_line, plan_b_admin_line = (
            self.budget_analytic_expense.budget_line_ids
        )
        self.assertBudgetLine(plan_a_line, committed=2000, achieved=0)
        self.assertBudgetLine(plan_b_line, committed=2000, achieved=0)
        self.assertBudgetLine(plan_b_admin_line, committed=1000, achieved=0)
        bill = self.purchase_order.invoice_ids
        bill.write({"invoice_date": "2019-01-10"})
        bill.action_post()
        self.assertBudgetLine(plan_a_line, committed=2000, achieved=400)
        self.assertBudgetLine(plan_b_line, committed=2000, achieved=1100)
        self.assertBudgetLine(plan_b_admin_line, committed=1000, achieved=500)
        reversal_wizard = (
            self.env["wizard.account.move.reverse"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"journal_id": bill.journal_id.id, "date": "2019-01-11"})
        )
        reversal = reversal_wizard.reverse_moves()
        self.env["account.move"].browse(reversal["res_id"]).action_post()
        self.assertBudgetLine(plan_a_line, committed=2000, achieved=0)
        self.assertBudgetLine(plan_b_line, committed=2000, achieved=0)
        self.assertBudgetLine(plan_b_admin_line, committed=1000, achieved=0)

    def test_budget_analytic_purchase_order_last_budget_day(self):
        plan_a_line, _plan_b_line, _plan_b_admin_line = (
            self.budget_analytic_expense.budget_line_ids
        )
        self.assertBudgetLine(plan_a_line, committed=2000, achieved=0)

        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-12-31 21:00:00",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()

        self.assertBudgetLine(plan_a_line, committed=3000, achieved=0)

        purchase_order.action_cancel()
        purchase_order.action_draft()
        purchase_order.date_order = "2020-01-01 00:00:00"
        purchase_order.action_confirm()

        self.assertBudgetLine(plan_a_line, committed=2000, achieved=0)

    def test_budget_report_with_purchase_order(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        plan_a_line = self.budget_analytic_both.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=-1000, achieved=0)

    def test_account_budget_company_shared(self):
        budget = self.env["budget.analytic"].create(
            {
                "name": "Budget Shared",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
                "company_id": False,
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 2000,
                            self.project_column_name: self.analytic_account_partner_a.id,
                        }
                    ),
                ],
            }
        )
        budget.action_budget_confirm()
        line = budget.budget_line_ids[0]

        company_a = self.company
        company_b = self.setup_other_company(name="other_company")["company"]

        self.env.user.write(
            {
                "company_ids": [(6, 0, [company_a.id, company_b.id])],
                "company_id": company_a.id,
            }
        )

        po_a = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "company_id": company_a.id,
                "date_order": "2025-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "price_unit": 1000,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        po_a.action_confirm()

        po_b = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "company_id": company_b.id,
                "date_order": "2025-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "price_unit": 1000,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        po_b.action_confirm()
        self.assertEqual(
            line.committed_amount, 2000.0, "Shared committed should be 2000"
        )
        self.assertEqual(line.achieved_amount, 0.0, "Shared achieved should be 1000")

        po_a.line_ids.qty_transferred = 0.5
        bill_a = self.env["account.move"].browse(po_a.create_invoice().id)
        bill_a.invoice_date = "2025-01-15"
        bill_a.sudo().action_post()

        po_b.line_ids.qty_transferred = 0.5
        bill_b = (
            self.env["account.move"]
            .with_company(company_b)
            .browse(po_b.create_invoice().id)
        )
        bill_b.invoice_date = "2025-01-15"
        bill_b.action_post()

        self.env["budget.line"].invalidate_model(
            ["committed_amount", "achieved_amount"]
        )
        self.assertEqual(
            line.committed_amount, 2000.0, "Shared committed should be 2000"
        )
        self.assertEqual(line.achieved_amount, 1000.0, "Shared achieved should be 1000")

        budget.company_id = company_a.id
        self.env["budget.line"].invalidate_model(
            ["committed_amount", "achieved_amount"]
        )

        self.assertEqual(
            line.committed_amount, 1000.0, "Company A committed should be 1000"
        )
        self.assertEqual(
            line.achieved_amount, 500.0, "Company A committed should be 1000"
        )

    def test_budget_analytic_expense_committed_amount_negative_price(self):
        self.purchase_order.action_cancel()
        self.purchase_order.action_draft()
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_b.id,
                            "price_unit": -10,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.action_confirm()
        purchase_order.write(
            {
                "line_ids": [
                    Command.update(
                        purchase_order.line_ids[0].id, {"qty_transferred": 1}
                    ),
                    Command.update(
                        purchase_order.line_ids[1].id, {"qty_transferred": 1}
                    ),
                ]
            }
        )
        purchase_order.create_invoice()
        purchase_order.invoice_ids.write({"invoice_date": "2019-01-10"})
        purchase_order.invoice_ids.action_post()

        plan_a_line = self.budget_analytic_expense.budget_line_ids[0]
        self.assertBudgetLine(plan_a_line, committed=90, achieved=90)

    def test_account_budget_overlapping_accounts(self):

        budget = self.env["budget.analytic"].create(
            {
                "name": "Test Budget",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 500,
                            self.project_column_name: self.analytic_account_partner_a.id,
                        }
                    ),
                    Command.create(
                        {
                            "budget_amount": 600,
                            self.department_column_name: self.analytic_account_administratif.id,
                        }
                    ),
                ],
            }
        )
        budget.action_budget_confirm()
        line = budget.budget_line_ids[0]

        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2025-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "analytic_distribution": {
                                f"{self.analytic_account_partner_a.id}, {self.analytic_account_administratif.id}": 100,
                            },
                            "quantity": 1,
                            "price_unit": 100,
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                        }
                    ),
                ],
            }
        )
        bill.action_post()

        self.assertBudgetLine(line, committed=100.0, achieved=100.0)

        action = line.action_view_budget_entries()
        report_lines = self.env["budget.report"].search(action["domain"])
        self.assertEqual(sum(line.committed for line in report_lines), 100.0)
