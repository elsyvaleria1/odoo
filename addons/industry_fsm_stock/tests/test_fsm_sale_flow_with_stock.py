from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.industry_fsm_sale.tests.common import TestFsmFlowSaleCommon


@tagged("-at_install", "post_install")
class TestFsmFlowSaleWithStock(TestFsmFlowSaleCommon):

    def test_fsm_flow(self):
        self.assertFalse(
            self.task.material_line_product_count,
            "No product should be linked to a new task",
        )
        with self.assertRaises(
            UserError, msg="Should not be able to get to material without customer set"
        ):
            self.task.action_fsm_view_material()
        self.task.write({"partner_id": self.partner_1.id})
        self.assertFalse(
            self.task.task_to_invoice, "Nothing should be invoiceable on task"
        )
        self.task.with_user(self.project_user).action_fsm_view_material()

        expected_product_count = 1
        self.service_product_delivered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        expected_product_count += 1
        self.service_product_delivered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        expected_product_count += 1
        self.consu_product_delivered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        expected_product_count += 1
        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        expected_product_count -= 1
        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_remove_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        expected_product_count += 1
        self.service_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        quantity_to_add = 5
        expected_product_count += quantity_to_add
        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).set_fsm_quantity(quantity_to_add)
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        values = {
            "task_id": self.task.id,
            "project_id": self.task.project_id.id,
            "date": datetime.now(),
            "name": "test timesheet",
            "user_id": self.env.uid,
            "unit_amount": 0.25,
            "employee_id": self.env["hr.employee"].create({"user_id": self.env.uid}).id,
        }
        self.env["account.analytic.line"].create(values)
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            "Timesheet should not appear in material",
        )

        self.assertFalse(self.task.fsm_done, "Task should not be validated")
        self.assertEqual(len(self.task.sale_order_id.line_ids), 4)

        order_line = self.task.sale_order_id.line_ids.filtered(
            lambda l: l.name == self.service_product_ordered.name
        )
        self.assertEqual(order_line.product_qty, 1)
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertTrue(self.task.fsm_done, "Task should be validated")
        self.assertEqual(
            self.task.sale_order_id.state, "done", "Sale order should be confirmed"
        )

        self.service_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).set_fsm_quantity(9)
        self.assertEqual(order_line.product_qty, 9)
        expected_product_count += 8
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        self.assertTrue(self.task.task_to_invoice, "Task should be invoiceable")
        invoice_ctx = self.task.action_create_invoice()["context"]
        invoice_wizard = (
            self.env["wizard.sale.order.invoice"].with_context(invoice_ctx).create({})
        )
        invoice_wizard.create_invoices()
        self.task.sale_order_id.invoice_ids.action_post()
        self.assertFalse(self.task.task_to_invoice, "Task should not be invoiceable")

        self.assertEqual(
            self.task.quotation_count,
            0,
            "0 quotation should be linked to the task since we don't create a quotation via the Create Quotation button.",
        )
        quotation_context = self.task.action_fsm_create_quotation()["context"]
        quotation = self.env["sale.order"].with_context(quotation_context).create({})
        self.assertEqual(quotation.task_id, self.task)
        self.task._compute_quotation_count()
        self.assertEqual(
            self.task.quotation_count,
            1,
            "1 quotation should be linked to the task since we create a quotation via the Create Quotation button.",
        )
        self.assertEqual(
            self.task.action_fsm_view_quotations()["res_id"],
            quotation.id,
            "Created quotation id should be in the action",
        )
