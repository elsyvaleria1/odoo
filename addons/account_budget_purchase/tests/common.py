from odoo.fields import Command

from odoo.addons.account_budget.tests.common import TestAccountBudgetCommon


class TestAccountBudgetPurchaseCommon(TestAccountBudgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        purchase_order = cls.env["purchase.order"].create(
            {
                "partner_id": cls.partner_a.id,
                "date_order": "2019-01-10",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                cls.analytic_account_partner_a.id: 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_a.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    cls.analytic_account_partner_a.id,
                                    cls.analytic_account_administratif.id,
                                ): 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_b.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                cls.analytic_account_partner_b.id: 100
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_b.id,
                            "product_qty": 10,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    cls.analytic_account_partner_b.id,
                                    cls.analytic_account_administratif.id,
                                ): 100
                            },
                        }
                    ),
                ],
            }
        )
        purchase_order.line_ids._compute_analytic_json()
        purchase_order.action_confirm()
        purchase_order.write(
            {
                "line_ids": [
                    Command.update(
                        purchase_order.line_ids.sorted()[0].id, {"qty_transferred": 1}
                    ),
                    Command.update(
                        purchase_order.line_ids.sorted()[1].id, {"qty_transferred": 3}
                    ),
                    Command.update(
                        purchase_order.line_ids.sorted()[2].id, {"qty_transferred": 6}
                    ),
                    Command.update(
                        purchase_order.line_ids.sorted()[3].id, {"qty_transferred": 5}
                    ),
                ]
            }
        )
        purchase_order.create_invoice()
        purchase_order.invoice_ids.write({"invoice_date": "2019-01-10"})
        cls.purchase_order = purchase_order

        account = cls.company_data["default_account_revenue"]
        cls.out_invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2019-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product_a.id,
                            "analytic_distribution": {
                                cls.analytic_account_partner_a.id: 100
                            },
                            "quantity": 2,
                            "price_unit": 100,
                            "account_id": account.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_a.id,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    cls.analytic_account_partner_a.id,
                                    cls.analytic_account_administratif.id,
                                ): 100
                            },
                            "quantity": 4,
                            "price_unit": 100,
                            "account_id": account.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_b.id,
                            "analytic_distribution": {
                                cls.analytic_account_partner_b.id: 100
                            },
                            "quantity": 7,
                            "price_unit": 100,
                            "account_id": account.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_b.id,
                            "analytic_distribution": {
                                "%s,%s"
                                % (
                                    cls.analytic_account_partner_b.id,
                                    cls.analytic_account_administratif.id,
                                ): 100
                            },
                            "quantity": 6,
                            "price_unit": 100,
                            "account_id": account.id,
                        }
                    ),
                ],
            }
        )

    def assertBudgetLine(self, budget_line, *, committed, achieved):
        budget_line.invalidate_recordset(["achieved_amount", "committed_amount"])
        self.assertRecordValues(
            budget_line, [{"committed_amount": committed, "achieved_amount": achieved}]
        )
