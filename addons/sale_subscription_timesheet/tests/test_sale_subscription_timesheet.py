from odoo import Command
from odoo.tests import freeze_time, tagged

from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)
from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("-at_install", "post_install")
class TestSubscriptionTask(TestSubscriptionCommon, TestCommonSaleTimesheet):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_deliver_timesheet = cls.env["product.product"].create(
            {
                "name": "Service Ordered, create task in global project",
                "standard_price": 30,
                "list_price": 90,
                "type": "service",
                "invoice_policy": "transferred",
                "uom_id": cls.uom_hour.id,
                "default_code": "SERV-ORDERED2",
                "service_type": "timesheet",
                "recurring_invoice": True,
                "service_tracking": "task_global_project",
                "project_id": cls.project_global.id,
                "taxes_id": False,
                "property_account_income_id": cls.account_sale.id,
            }
        )
        cls.subscription_timesheet = cls.env["sale.order"].create(
            {
                "name": "TestSubscriptionWithTimeSheet",
                "is_subscription": True,
                "plan_id": cls.plan_month.id,
                "notes": "original subscription description",
                "partner_id": cls.user_portal.partner_id.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product_deliver_timesheet.id,
                            "product_qty": 1,
                        }
                    ),
                ],
            }
        )

    def test_sub_timesheet_create_recurring_tasks(self):

        self.env.user.group_ids += self.env.ref("project.group_project_recurring_tasks")
        self.project_global.allow_recurring_tasks = True
        with freeze_time("2024-10-01"):
            self.subscription_timesheet.action_confirm()
            task = self.subscription_timesheet.tasks_ids
            self.assertTrue(task, "A new task should be created")
            self.assertEqual(
                self.subscription_timesheet.line_ids.qty_transferred,
                0,
                "No delivery before creating the first recurring invoice",
            )
            self.env["account.analytic.line"].create(
                {
                    "name": "Test Line",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 4,
                    "employee_id": self.employee_user.id,
                }
            )
            self.assertEqual(
                self.subscription_timesheet.line_ids.qty_transferred,
                4,
                "Product should be delivered after creating the recurring invoice",
            )
        with freeze_time("2024-10-01"):
            self.env["account.analytic.line"].create(
                {
                    "name": "Test Line",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 6,
                    "employee_id": self.employee_user.id,
                }
            )
            self.subscription_timesheet.line_ids.with_context(
                arj=True
            )._compute_qty_transferred()
            self.assertEqual(
                self.subscription_timesheet.line_ids.qty_transferred,
                10,
                "The product should be delivered",
            )
            task.state = "done"
            self.subscription_timesheet.invalidate_recordset(["tasks_ids"])
            task = self.subscription_timesheet.tasks_ids - task
            self.assertTrue(task)
        with freeze_time("2024-11-01"):
            inv = self.subscription_timesheet._create_recurring_invoice()
            self.assertEqual(
                inv.amount_untaxed,
                900,
                "The amount depends on the timesheet (90 per hour)",
            )
        with freeze_time("2024-11-15"):
            self.env["account.analytic.line"].create(
                {
                    "name": "Test Line",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 50,
                    "employee_id": self.employee_user.id,
                }
            )
            self.assertEqual(
                self.subscription_timesheet.line_ids.qty_transferred,
                50,
                "The product should be delivered",
            )
        with freeze_time("2024-12-01"):
            inv = self.subscription_timesheet._create_recurring_invoice()
            task.state = "done"
            self.subscription_timesheet.invalidate_recordset(["tasks_ids"])
            task = self.subscription_timesheet.tasks_ids - task
            self.assertTrue(task)
            self.assertEqual(
                inv.amount_untaxed,
                4500,
                "The amount depends on the timesheet (90 per hour)",
            )
            self.assertEqual(len(task), 2, "Two tasks are created automatically")

    def test_sub_timesheet_order_invoice_product(self):
        self.product_order_timesheet2.recurring_invoice = True

        with freeze_time("2025-02-15"):
            subscription_timesheet = self.env["sale.order"].create(
                {
                    "name": "Test",
                    "plan_id": self.plan_month.id,
                    "partner_id": self.user_portal.partner_id.id,
                    "start_date": "2025-02-01",
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_order_timesheet2.id,
                                "product_qty": 10,
                            }
                        ),
                    ],
                }
            )
            subscription_timesheet.action_confirm()
            task = subscription_timesheet.tasks_ids
            self.env["account.analytic.line"].create(
                [
                    {
                        "name": "Timesheet before subscription period",
                        "project_id": task.project_id.id,
                        "task_id": task.id,
                        "unit_amount": 2,
                        "employee_id": self.employee_user.id,
                        "date": "2025-01-15",
                    },
                    {
                        "name": "Timesheet during subscription period",
                        "project_id": task.project_id.id,
                        "task_id": task.id,
                        "unit_amount": 2,
                        "employee_id": self.employee_user.id,
                        "date": "2025-02-15",
                    },
                ]
            )
            self.env["sale.order"]._cron_recurring_create_invoice()
            self.assertEqual(
                subscription_timesheet.line_ids.qty_transferred,
                2,
                "2 hours delivered for the February period",
            )

    @freeze_time("2025-03-03")
    def test_sub_invoice_timesheet(self):
        self.subscription_timesheet.action_confirm()
        task = self.subscription_timesheet.tasks_ids
        _, present_timesheet = self.env["account.analytic.line"].create(
            [
                {
                    "name": "Test Line",
                    "date": "2025-02-01",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 3,
                    "employee_id": self.employee_user.id,
                },
                {
                    "name": "Test Line",
                    "date": "2025-03-03",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 4,
                    "employee_id": self.employee_user.id,
                },
            ]
        )
        self.subscription_timesheet._create_recurring_invoice()

        self.assertTrue(self.subscription_timesheet.last_invoice_date)
        moves = (
            self.env["wizard.sale.order.invoice"]
            .with_context(
                {
                    "active_model": "sale.order",
                    "active_ids": [self.subscription_timesheet.id],
                    "active_id": self.subscription_timesheet.id,
                }
            )
            .create({"advance_payment_method": "delivered"})
            .create_invoices()
        )

        invoice = self.env["account.move"].browse(moves["res_id"])
        self.assertEqual(len(invoice.timesheet_ids), 1)
        self.assertEqual(
            invoice.invoice_line_ids.quantity, present_timesheet.unit_amount
        )
        self.assertEqual(invoice.timesheet_ids.id, present_timesheet.id)

    @freeze_time("2025-08-03")
    def test_sub_link_timesheet_to_invoice(self):
        subscription = self.env["sale.order"].create(
            {
                "name": "CopyTestSubscriptionWithTimeSheet",
                "is_subscription": True,
                "plan_id": self.plan_month.id,
                "notes": "original subscription description",
                "partner_id": self.user_portal.partner_id.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_deliver_timesheet.id,
                            "product_qty": 6,
                        }
                    ),
                ],
                "start_date": "2025-07-01",
            }
        )
        subscription.action_confirm()
        subscription.write({"next_invoice_date": "2025-08-01"})

        task = subscription.tasks_ids
        self.env["account.analytic.line"].create(
            [
                {
                    "name": "Test Include Line",
                    "date": "2025-07-01",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 3,
                    "employee_id": self.employee_user.id,
                },
                {
                    "name": "Test Line",
                    "date": "2025-07-31",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 3,
                    "employee_id": self.employee_user.id,
                },
                {
                    "name": "Test Exclude Line",
                    "date": "2025-08-01",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 4,
                    "employee_id": self.employee_user.id,
                },
            ]
        )

        moves = (
            self.env["wizard.sale.order.invoice"]
            .with_context(
                {
                    "active_model": "sale.order",
                    "active_ids": [subscription.id],
                    "active_id": subscription.id,
                }
            )
            .create({"advance_payment_method": "delivered"})
            .create_invoices()
        )
        invoice = self.env["account.move"].browse(moves["res_id"])

        self.assertEqual(len(invoice.timesheet_ids), 2)

    @freeze_time("2025-08-03")
    def test_invoice_orders_if_delivery_qty(self):
        subscription = self.env["sale.order"].create(
            {
                "name": "CopyTestSubscriptionWithTimeSheet",
                "is_subscription": True,
                "plan_id": self.plan_month.id,
                "notes": "original subscription description",
                "partner_id": self.user_portal.partner_id.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_deliver_timesheet.id,
                            "product_qty": 0,
                        }
                    ),
                ],
                "start_date": "2025-07-01",
            }
        )
        subscription.action_confirm()
        subscription.write({"next_invoice_date": "2025-08-01"})

        task = self.env["project.task"].create(
            {
                "name": "Test Task",
                "project_id": self.project_global.id,
                "sale_order_id": subscription.id,
                "sale_line_id": subscription.line_ids[0].id,
            }
        )
        timesheet = self.env["account.analytic.line"].create(
            [
                {
                    "name": "Test Include Line",
                    "date": "2025-07-15",
                    "project_id": task.project_id.id,
                    "task_id": task.id,
                    "unit_amount": 3,
                    "employee_id": self.employee_user.id,
                },
            ]
        )

        self.env["sale.order"]._cron_recurring_create_invoice()

        self.assertTrue(subscription.invoice_ids)
        self.assertEqual(
            subscription.invoice_ids.invoice_line_ids[0].quantity, timesheet.unit_amount
        )
