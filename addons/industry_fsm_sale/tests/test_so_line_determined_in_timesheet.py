from odoo import Command
from odoo.tests import tagged
from odoo.tools import float_round

from .common import TestFsmFlowSaleCommon


@tagged("-at_install", "post_install")
class TestSoLineDeterminedInTimesheet(TestFsmFlowSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.fsm_so = (
            cls.env["sale.order"]
            .with_context(mail_notrack=True, mail_create_nolog=True)
            .create(
                {
                    "partner_id": cls.partner_1.id,
                    "partner_invoice_id": cls.partner_1.id,
                    "partner_shipping_id": cls.partner_1.id,
                    "line_ids": [
                        Command.create(
                            {
                                "name": cls.product_delivery_timesheet1.name,
                                "product_id": cls.product_delivery_timesheet1.id,
                                "product_qty": 10,
                                "price_unit": cls.product_delivery_timesheet1.list_price,
                            }
                        ),
                        Command.create(
                            {
                                "product_id": cls.product_delivery_timesheet2.id,
                                "product_qty": 5,
                                "price_unit": cls.product_delivery_timesheet2.list_price,
                            }
                        ),
                        Command.create(
                            {
                                "product_id": cls.product_delivery_timesheet3.id,
                                "product_qty": 5,
                                "price_unit": cls.product_delivery_timesheet3.list_price,
                            }
                        ),
                    ],
                }
            )
        )
        cls.fsm_so.action_confirm()

    def test_sol_determined_when_fsm_project_is_employee_rate(self):
        task = (
            self.env["project.task"]
            .with_context(
                {
                    "mail_create_nolog": True,
                    "default_project_id": self.fsm_project_employee_rate.id,
                    "default_user_ids": self.project_user,
                }
            )
            .create(
                {
                    "sale_line_id": self.fsm_so.line_ids[:1].id,
                    "name": "Fsm Task",
                }
            )
        )

        employee_manager_timesheet = self.env["account.analytic.line"].create(
            {
                "name": "/",
                "employee_id": self.employee_manager.id,
                "unit_amount": 1.0,
                "task_id": task.id,
                "project_id": self.fsm_project_employee_rate.id,
            }
        )
        self.assertEqual(
            employee_manager_timesheet.so_line,
            task.sale_line_id,
            "This timesheet should have the same SOL than the one in the task because the employee is not in the employee mappings.",
        )
        self.assertEqual(
            task.sale_line_id.qty_transferred,
            1.0,
            "The quantity delivered should be equal to 1 for the SOL linked to the task.",
        )

        employee_user3_timesheet = self.env["account.analytic.line"].create(
            {
                "name": "/",
                "employee_id": self.employee_user3.id,
                "unit_amount": 2.0,
                "task_id": task.id,
                "project_id": self.fsm_project_employee_rate.id,
            }
        )

        employee_user3_mapping = (
            self.fsm_project_employee_rate.sale_line_employee_ids.filtered(
                lambda mapping: (
                    mapping.employee_id == employee_user3_timesheet.employee_id
                )
            )
        )

        sol = self.fsm_so.line_ids.filtered(
            lambda sol: (
                sol.product_id == employee_user3_mapping.timesheet_product_id
                and sol.price_unit == employee_user3_mapping.price_unit
            )
        )
        self.assertEqual(
            employee_user3_timesheet.so_line,
            sol,
            "The SOL linked to the timesheet should be the one containing the service product with the same price unit defined for this employee in the mappings.",
        )
        self.assertEqual(
            sol.qty_transferred,
            2.0,
            "The quantity delivered for this SOL should be the unit_amount of the timesheet, that is 2 hours.",
        )

        employee_user_timesheet = self.env["account.analytic.line"].create(
            {
                "name": "/",
                "employee_id": self.employee_user.id,
                "unit_amount": 3.0,
                "task_id": task.id,
                "project_id": self.fsm_project_employee_rate.id,
            }
        )

        employee_user_mapping = (
            self.fsm_project_employee_rate.sale_line_employee_ids.filtered(
                lambda mapping: (
                    mapping.employee_id == employee_user_timesheet.employee_id
                )
            )
        )

        self.assertFalse(
            any(
                sol.product_id == employee_user_mapping.timesheet_product_id
                and sol.price_unit == employee_user_mapping.price_unit
                for sol in self.fsm_so.line_ids
            ),
            "No SOL contains the product and the same price unit than the mapping for this employee user.",
        )
        self.assertFalse(
            employee_user_timesheet.so_line,
            "The SOL linked to the timesheet should be False as there exists a mapping defined for this employee in the project but no SOL contains the same product and the same price unit than in this mapping. Note that the SOL will only be set when the task will be validated.",
        )

        sol = self.fsm_so.line_ids.filtered(
            lambda sol: sol.product_id == self.product_delivery_timesheet3
        )[:1]
        task.write(
            {
                "sale_line_id": sol.id,
            }
        )
        self.assertTrue(
            task.sale_line_id == employee_manager_timesheet.so_line == sol,
            "The SOL in the timesheet of employee manager should be the one defined in the task.",
        )
        self.assertFalse(
            employee_user_timesheet.so_line,
            "The SOL in the timesheet of employee user should remain False as the task was not validated yet.",
        )
        self.assertNotEqual(
            employee_user3_timesheet.so_line,
            task.sale_line_id,
            "The SOL in the timesheet of employee user should remain the same than before and be not the one in the task.",
        )

        mappings_count = len(self.fsm_project_employee_rate.sale_line_employee_ids)
        self.env["project.sale.line.employee.map"].create(
            {
                "employee_id": self.employee_manager.id,
                "timesheet_product_id": self.product_order_timesheet1.id,
                "price_unit": 150,
                "project_id": self.fsm_project_employee_rate.id,
            }
        )
        self.assertEqual(
            len(self.fsm_project_employee_rate.sale_line_employee_ids),
            mappings_count + 1,
            "The mapping for the employee manager should added in the employee mappings.",
        )

        self.assertFalse(
            employee_manager_timesheet.so_line,
            "The SOL linked to the timesheet should be False as there exists a mapping defined for the employee manager in the project but no SOL contains the same product and the same price unit than in this mapping. Note that the SOL will only be set when the task will be validated",
        )

    def test_fsm_sale_rounding(self):
        self.task.write({"partner_id": self.partner_1.id})
        product_qty = 0.333333
        quantity_precision = self.env["decimal.precision"].get_precision("Product Unit")
        values = {
            "task_id": self.task.id,
            "project_id": self.task.project_id.id,
            "name": "test timesheet",
            "user_id": self.env.uid,
            "unit_amount": product_qty,
            "employee_id": self.employee_user2.id,
        }
        self.env["account.analytic.line"].create(values)

        self.task.with_user(self.project_user).action_fsm_validate()
        order = self.task.sale_order_id

        expected_price_subtotal = order.line_ids.price_unit * float_round(
            product_qty, precision_digits=quantity_precision
        )
        self.assertAlmostEqual(
            order.line_ids.price_subtotal,
            expected_price_subtotal,
            delta=quantity_precision,
            msg="Order line subtotal is not correct",
        )

    def test_sol_determined_when_fsm_project_is_employee_rate_after_task_validation(
        self,
    ):

        task = (
            self.env["project.task"]
            .with_context(
                {
                    "mail_create_nolog": True,
                    "default_project_id": self.fsm_project_employee_rate.id,
                    "default_user_ids": self.project_user,
                }
            )
            .create(
                {
                    "sale_line_id": self.fsm_so.line_ids[:1].id,
                    "name": "Fsm Task",
                }
            )
        )

        employee_manager_timesheet, employee_user_timesheet = self.env[
            "account.analytic.line"
        ].create(
            [
                {
                    "name": "/",
                    "employee_id": employee_id,
                    "unit_amount": amount,
                    "task_id": task.id,
                    "project_id": self.fsm_project_employee_rate.id,
                }
                for employee_id, amount in [
                    (self.employee_manager.id, 1.0),
                    (self.employee_user.id, 3.0),
                ]
            ]
        )

        task.with_user(self.project_user).action_fsm_validate()

        employee_user_mapping = (
            self.fsm_project_employee_rate.sale_line_employee_ids.filtered(
                lambda mapping: (
                    mapping.employee_id == employee_user_timesheet.employee_id
                )
            )
        )
        sol = self.fsm_so.line_ids.filtered(
            lambda s: (
                s.product_id == employee_user_mapping.timesheet_product_id
                and s.price_unit == employee_user_mapping.price_unit
            )
        )
        self.assertEqual(
            employee_user_timesheet.so_line,
            sol,
            "The SOL linked to the timesheet should be the one containing the service product with the same price unit defined for this employee in the mappings.",
        )
        self.assertEqual(
            sol.qty_transferred,
            3.0,
            "The quantity delivered for this SOL should be the unit_amount of the timesheet, that is 3 hours.",
        )

        self.assertEqual(
            employee_manager_timesheet.so_line,
            task.sale_line_id,
            "This timesheet should have the same SOL than the one in the task because the employee is not in the employee mappings.",
        )
        self.assertEqual(
            task.sale_line_id.qty_transferred,
            1.0,
            "The quantity delivered should be equal to 1 for the SOL linked to the task.",
        )

    def test_sol_determined_on_timesheet_with_task_is_under_warranty(self):
        warranty_task, without_warranty_task = (
            self.env["project.task"]
            .with_context(
                {
                    "mail_create_nolog": True,
                    "default_user_ids": self.project_user,
                }
            )
            .create(
                [
                    {
                        "name": "Fsm Task 1",
                        "project_id": self.fsm_project_employee_rate.id,
                        "under_warranty": True,
                        "timesheet_ids": [
                            Command.create(
                                {
                                    "name": "/",
                                    "employee_id": self.employee_user.id,
                                    "unit_amount": 20,
                                }
                            )
                        ],
                    },
                    {
                        "name": "Fsm Task 2",
                        "project_id": self.fsm_project_employee_rate.id,
                        "timesheet_ids": [
                            Command.create(
                                {
                                    "name": "/",
                                    "employee_id": self.employee_user.id,
                                    "unit_amount": 20,
                                }
                            )
                        ],
                    },
                ]
            )
        )

        self.consu_product_delivered.with_context(
            {"fsm_task_id": warranty_task.id}
        ).set_fsm_quantity(2)
        self.consu_product_delivered.with_context(
            {"fsm_task_id": without_warranty_task.id}
        ).set_fsm_quantity(2)

        warranty_task.action_fsm_validate()
        self.assertFalse(
            warranty_task.timesheet_ids.so_line,
            "The timesheet should not be linked to a SOL.",
        )
        self.assertFalse(
            warranty_task.sale_line_id, "The task should not be linked to a SOL."
        )

        without_warranty_task.action_fsm_validate()
        self.assertTrue(
            without_warranty_task.timesheet_ids.so_line,
            "The timesheet should be linked to a SOL.",
        )
        self.assertTrue(
            without_warranty_task.sale_line_id, "The task should be linked to a SOL."
        )
