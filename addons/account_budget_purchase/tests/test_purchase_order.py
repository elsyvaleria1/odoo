from datetime import datetime

from odoo import Command
from odoo.tests import tagged
from odoo.tools import SQL

from .common import TestAccountBudgetCommon, TestAccountBudgetPurchaseCommon


@tagged("post_install", "-at_install")
class TestPurchaseOrder(TestAccountBudgetPurchaseCommon):
    def test_access_purchase_order(self):

        self.budget_analytic_expense.action_budget_confirm()
        purchase_partner = self.env["res.partner"].create({"name": "Purchaser"})
        purchase_user = self.env["res.users"].create(
            {
                "login": "Purchaser",
                "partner_id": purchase_partner.id,
                "group_ids": [
                    Command.set(self.env.ref("purchase.group_purchase_manager").ids)
                ],
            }
        )

        self.assertFalse(
            self.purchase_order.with_user(purchase_user).line_ids.budget_line_ids,
            " Purchase Order should be accessible by purchase manager even without accounting rights. ",
        )

    def test_purchase_order_is_above_budget(self):
        self.budget_analytic_expense.action_budget_confirm()
        po_1 = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 1000.0,
                            "product_qty": 100,
                            "analytic_distribution": {
                                self.analytic_account_administratif.id: 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_b.id,
                            "price_unit": 1000.0,
                            "product_qty": 1,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    self.analytic_account_partner_b.id,
                                    self.analytic_account_administratif.id,
                                ): 100
                            },
                        }
                    ),
                ],
            }
        )
        self.assertFalse(po_1.is_above_budget)
        self.assertFalse(po_1.line_ids[0].is_above_budget)
        self.assertFalse(po_1.line_ids[1].is_above_budget)
        po_2 = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 1000.0,
                            "product_qty": 100,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    self.analytic_account_partner_b.id,
                                    self.analytic_account_administratif.id,
                                ): 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_b.id,
                            "price_unit": 1000.0,
                            "product_qty": 1,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    self.analytic_account_partner_b.id,
                                    self.analytic_account_administratif.id,
                                ): 100
                            },
                        }
                    ),
                ],
            }
        )
        self.assertTrue(po_2.is_above_budget)
        self.assertTrue(po_2.line_ids[0].is_above_budget)
        self.assertFalse(po_2.line_ids[1].is_above_budget)

    def test_the_report_date_column_stays_a_date(self):
        report = self.env["budget.report"]
        self.env.cr.execute(SQL("SELECT * FROM (%s) t LIMIT 0", report._table_query))
        type_code = {
            column.name: column.type_code for column in self.env.cr.description
        }["date"]
        self.env.cr.execute("SELECT typname FROM pg_type WHERE oid = %s", (type_code,))
        self.assertEqual(self.env.cr.fetchone()[0], "date")

        self.budget_analytic_expense.action_budget_confirm()
        report.invalidate_model()
        for value in report.search([("line_type", "=", "committed")]).mapped("date"):
            self.assertNotIsInstance(value, datetime)

    def test_a_commitment_under_no_budget_is_still_reported(self):
        report = self.env["budget.report"]
        orphan_account = self.env["account.analytic.account"].create(
            {
                "name": "outside every budget",
                "plan_id": self.analytic_plan_projects.id,
            }
        )
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-06-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 3,
                            "name": "uncovered commitment",
                            "analytic_distribution": {orphan_account.id: 100},
                        }
                    )
                ],
            }
        )
        order.action_confirm()

        rows = report.search([("description", "=", "uncovered commitment")])
        self.assertEqual(len(rows), 1, "an uncovered commitment is reported once")
        self.assertFalse(rows.budget_analytic_id, "and attributed to no budget")

    def test_a_new_budget_reaches_existing_orders(self):
        account = self.env["account.analytic.account"].create(
            {"name": "late budget", "plan_id": self.analytic_plan_projects.id}
        )
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-06-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 5,
                            "price_unit": 100.0,
                            "name": "late budget line",
                            "analytic_distribution": {account.id: 100},
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        self.assertFalse(order.line_ids.budget_line_ids)
        self.assertFalse(order.is_above_budget)

        budget = self.env["budget.analytic"].create(
            {
                "name": "Late 2019",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 1.0,
                            self.project_column_name: account.id,
                        }
                    )
                ],
            }
        )
        budget.action_budget_confirm()

        self.assertEqual(
            order.line_ids.budget_line_ids,
            budget.budget_line_ids,
            "a budget created after the order must reach it with no manual invalidation",
        )
        self.assertTrue(order.is_above_budget)
        self.assertTrue(order.line_ids.is_above_budget)

    def test_multi_key_distribution_reaches_every_budget(self):
        self.budget_analytic_expense.action_budget_confirm()
        department_budget = self.env["budget.analytic"].create(
            {
                "name": "Budget 2019: Administratif 2",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
                "state": "draft",
                "user_id": self.env.ref("base.user_admin").id,
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 2000,
                            self.department_column_name: self.analytic_account_administratif_2.id,
                        }
                    ),
                ],
            }
        )
        department_budget.action_budget_confirm()

        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-06-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 50,
                                self.analytic_account_administratif_2.id: 50,
                            },
                        }
                    )
                ],
            }
        )
        line = order.line_ids
        partner_a_budget_line = self.budget_analytic_expense.budget_line_ids.filtered(
            lambda b: (
                b[self.project_column_name] == self.analytic_account_partner_a
                and not b[self.department_column_name]
            )
        )
        self.assertEqual(
            line.budget_line_ids,
            partner_a_budget_line | department_budget.budget_line_ids,
            "a line whose analytic_distribution has two separate keys must "
            "reach the budget line for EVERY key, not just the first",
        )


@tagged("post_install", "-at_install")
class TestPurchaseOrderBudgetContamination(TestAccountBudgetCommon):

    def test_uncommitted_amount_uses_discounted_price(self):
        budget = self.env["budget.analytic"].create(
            {
                "name": "Budget 2019: Discount",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
                "state": "draft",
                "user_id": self.env.ref("base.user_admin").id,
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 900,
                            self.project_column_name: self.analytic_account_partner_a.id,
                        }
                    ),
                ],
            }
        )
        budget.action_budget_confirm()

        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-06-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "price_unit": 1000,
                            "discount": 50,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    )
                ],
            }
        )
        line = order.line_ids
        self.assertEqual(
            line.price_subtotal, 500.0, "sanity: the discount actually applies"
        )
        self.assertFalse(
            line.is_above_budget,
            "the line's real, discounted value (500) is under the 900 budget, "
            "so is_above_budget must use the discounted basis, not raw price_unit",
        )
        self.assertFalse(order.is_above_budget)

    def test_uncommitted_amount_does_not_leak_across_budgets(self):
        small_budget = self.env["budget.analytic"].create(
            {
                "name": "Budget 2019: Small",
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "budget_type": "expense",
                "state": "draft",
                "user_id": self.env.ref("base.user_admin").id,
                "budget_line_ids": [
                    Command.create(
                        {
                            "budget_amount": 1000,
                            self.project_column_name: self.analytic_account_partner_a.id,
                        }
                    ),
                ],
            }
        )
        small_budget.action_budget_confirm()
        self.budget_analytic_expense.action_budget_confirm()

        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "date_order": "2019-06-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                            "price_unit": 100,
                            "analytic_distribution": {
                                self.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_b.id,
                            "product_qty": 1,
                            "price_unit": 8000,
                            "analytic_distribution": {
                                self.analytic_account_partner_b.id: 100
                            },
                        }
                    ),
                ],
            }
        )
        line_a, line_b = order.line_ids
        self.assertFalse(
            line_a.is_above_budget, "line under budget A alone (100 vs 1000)"
        )
        self.assertFalse(
            line_b.is_above_budget, "line under budget B alone (8000 vs 9000)"
        )
        self.assertFalse(
            order.is_above_budget,
            "line B's large uncommitted amount must not leak into budget A's "
            "unrelated threshold check",
        )
