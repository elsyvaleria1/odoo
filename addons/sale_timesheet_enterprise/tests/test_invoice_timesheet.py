from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("-at_install", "post_install")
class TestInvoiceTimesheet(TestCommonSaleTimesheet):
    def test_timesheet_transfer_sol(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sale.invoiced_timesheet", "approved"
        )

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_invoice_id": self.partner_a.id,
                "partner_shipping_id": self.partner_a.id,
            }
        )
        so_line_product_1 = self.env["sale.order.line"].create(
            {
                "product_id": self.product_delivery_timesheet3.id,
                "order_id": sale_order.id,
            }
        )

        sale_order.action_confirm()

        task_id = self.env["project.task"].search(
            [("sale_line_id", "=", so_line_product_1.id)]
        )
        project_id = self.env["project.project"].search(
            [("sale_line_id", "=", so_line_product_1.id)]
        )
        self.assertEqual(
            len(task_id), 1, "On SO confirmation, a task should have been created"
        )
        self.assertEqual(
            len(project_id), 1, "On SO confirmation, a project should have been created"
        )

        so_line_product_2 = self.env["sale.order.line"].create(
            {
                "product_id": self.product_delivery_timesheet1.id,
                "order_id": sale_order.id,
            }
        )

        so_line_product_3 = self.env["sale.order.line"].create(
            {
                "product_id": self.product_delivery_timesheet2.id,
                "order_id": sale_order.id,
            }
        )

        timesheet_1 = self.env["account.analytic.line"].create(
            {
                "date": fields.Date.today() - timedelta(days=1),
                "name": "Line 1",
                "project_id": project_id.id,
                "task_id": task_id.id,
                "unit_amount": 2,
                "employee_id": self.employee_manager.id,
            }
        )
        timesheet_2 = self.env["account.analytic.line"].create(
            {
                "date": fields.Date.today() - timedelta(days=1),
                "name": "Line 2",
                "project_id": project_id.id,
                "task_id": task_id.id,
                "unit_amount": 3,
                "employee_id": self.employee_user.id,
            }
        )

        timesheet_1.action_validate_timesheet()
        self.assertEqual(
            so_line_product_1.qty_transferred,
            2,
            "Timesheet 1 is validated, so 2 hours must be delivered",
        )

        invoice_1 = sale_order._create_invoices()
        invoice_1.action_cancel()

        self.assertEqual(so_line_product_1.qty_invoiced, 0, "No hours must be invoiced")
        self.assertEqual(
            timesheet_1.timesheet_invoice_id,
            invoice_1,
            "Timesheet 1 is linked to invoice 1",
        )
        self.assertFalse(
            timesheet_2.timesheet_invoice_id, "Timesheet 2 is not linked to invoice"
        )

        invoice_2 = sale_order._create_invoices()

        self.assertEqual(
            timesheet_1.timesheet_invoice_id,
            invoice_2,
            "Timesheet 1 is linked to invoice 2",
        )
        self.assertFalse(
            timesheet_2.timesheet_invoice_id, "Timesheet 2 is not linked to invoice"
        )
        self.assertEqual(
            so_line_product_1.qty_invoiced_draft,
            2,
            "2 hours must be on the draft invoice",
        )
        self.assertEqual(
            so_line_product_1.qty_transferred,
            2,
            "Timesheet 1 is validated, so 2 hours must be delivered",
        )

        timesheet_2.action_validate_timesheet()
        self.assertEqual(
            so_line_product_1.qty_invoiced_draft,
            2,
            "2 hours must be on the draft invoice (only timsheet 1)",
        )
        self.assertEqual(
            so_line_product_1.qty_transferred,
            5,
            "Timesheet 1 and 2 are validated, so 5 hours must be delivered",
        )
        self.assertFalse(
            so_line_product_2.qty_invoiced,
            "No hours invoiced (as no timsheet linked to this so_line)",
        )
        self.assertFalse(
            so_line_product_2.qty_transferred,
            "No hours delivered (as no timsheet linked to this so_line)",
        )

        task_id.sale_line_id = so_line_product_3
        self.assertEqual(
            timesheet_2.so_line,
            so_line_product_1,
            "SO line must remain same for validated Timesheet",
        )

        timesheet_2.action_invalidate_timesheet()

        task_id.sale_line_id = so_line_product_2
        self.assertEqual(
            timesheet_2.so_line,
            so_line_product_2,
            "SO line must change for Timesheet which are Draft",
        )

        timesheet_2.action_validate_timesheet()
        self.assertEqual(
            so_line_product_1.qty_invoiced_draft,
            2,
            "2 hours must be on the draft invoice (only timsheet 1)",
        )
        self.assertEqual(
            so_line_product_1.qty_transferred,
            2,
            "Timesheet 1 stay on this so_line (as already invoiced), so 2 hours must be delivered",
        )
        self.assertFalse(so_line_product_2.qty_invoiced, "No hours yet invoiced")
        self.assertEqual(
            so_line_product_2.qty_transferred,
            3,
            "Timesheet 2 is linked to this new so_line (3 hours delivered)",
        )

        invoice_3 = sale_order._create_invoices()
        self.assertEqual(
            so_line_product_1.qty_invoiced_draft,
            2,
            "2 hours must be on the draft invoice (only timsheet 1)",
        )
        self.assertEqual(
            so_line_product_1.qty_transferred,
            2,
            "Timesheet 1 stay on this so_line (as already invoiced), so 2 hours must be delivered",
        )
        self.assertEqual(
            so_line_product_2.qty_invoiced_draft,
            3,
            "Timesheet 2 is linked to this so_line (3 hours on the draft invoice)",
        )
        self.assertEqual(
            so_line_product_2.qty_transferred,
            3,
            "Timesheet 2 is linked to this so_line (3 hours delivered)",
        )

        self.assertEqual(
            timesheet_1.timesheet_invoice_id,
            invoice_2,
            "Timesheet 1 is always linked to invoice 2",
        )
        self.assertEqual(
            timesheet_2.timesheet_invoice_id,
            invoice_3,
            "Timesheet 2 is linked to invoice 3",
        )
