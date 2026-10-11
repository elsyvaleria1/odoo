import base64
import io
from datetime import datetime

from PIL import Image

from odoo.tests import tagged

from odoo.addons.industry_fsm_sale.tests.common import TestFsmFlowSaleCommon


@tagged("post_install", "-at_install")
class TestTimerButtons(TestFsmFlowSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "My Customer"})
        cls.env.company.hr_timesheet_config_id.timesheet_encode_uom_id = cls.env.ref(
            "base.product_uom_hour"
        )
        cls.product_service = cls.env["product.product"].create(
            {
                "name": "My Service Product",
                "sale_ok": True,
                "type": "service",
                "lst_price": 15,
            }
        )
        cls.product_material = cls.env["product.product"].create(
            {
                "name": "My Material Product",
                "sale_ok": True,
                "invoice_policy": "ordered",
                "lst_price": 5,
                "service_type": "manual",
            }
        )
        cls.project = cls.env["project.project"].create(
            {
                "name": "My Project",
                "partner_id": cls.customer.id,
                "allow_timesheets": True,
                "allow_worksheets": True,
                "allow_material": True,
                "allow_billable": True,
                "timesheet_product_id": cls.product_service.id,
                "is_fsm": True,
                "company_id": cls.env.company.id,
            }
        )
        cls.task = cls.env["project.task"].create(
            {
                "name": "My Task",
                "project_id": cls.project.id,
                "partner_id": cls.customer.id,
                "worksheet_template_id": cls.env.ref(
                    "industry_fsm_report.fsm_worksheet_template"
                ).id,
            }
        )
        cls.employee = (
            cls.env["hr.employee"]
            .with_company(cls.env.company)
            .create(
                {
                    "name": "Employee Default",
                    "user_id": cls.env.uid,
                }
            )
        )

    def test_timer_buttons_01(self):
        self.task.fsm_done = True
        self.assertFalse(self.task.display_timesheet_timer)

    def test_timer_buttons_02(self):
        self.assertFalse(self.task.timer_start)
        self.task.action_timer_start()
        self.assertTrue(self.task.timer_start)
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertFalse(self.task.display_send_report_secondary)
        self.assertFalse(self.task.display_mark_as_done_primary)
        self.assertFalse(self.task.display_mark_as_done_secondary)
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)
        self.task.action_timer_stop()

    def test_timer_buttons_03(self):
        self.project.allow_timesheets = False
        self.assertFalse(self.task.display_timesheet_timer)

    def test_timer_buttons_04(self):
        company_2 = self.env["res.company"].create(
            {
                "name": "Company 2",
            }
        )
        company_3 = self.env["res.company"].create(
            {
                "name": "Company 3",
            }
        )

        task = self.task.with_context(
            allowed_company_ids=[company_3.id, company_2.id, self.env.company.id]
        )

        self.project.write(
            {
                "privacy_visibility": "followers",
                "message_partner_ids": self.env.user.partner_id,
            }
        )
        self.env.user.write(
            {
                "group_ids": [(4, self.env.ref("project.group_project_manager").id)],
            }
        )

        self.assertTrue(task.display_timesheet_timer)

        self.env["hr.employee"].with_company(company_2).create(
            {
                "name": "Employee 2",
                "user_id": self.env.uid,
            }
        )
        task._compute_display_timesheet_timer()
        self.assertFalse(task.display_timesheet_timer)

    def test_send_sign_report_buttons_01(self):

        self.assertEqual(self.task.display_enabled_conditions_count, 3)
        self.project.allow_worksheets = False
        self.assertEqual(self.task.display_enabled_conditions_count, 2)
        self.project.allow_material = False
        self.assertEqual(self.task.display_enabled_conditions_count, 1)
        self.project.allow_timesheets = False
        self.assertEqual(self.task.display_enabled_conditions_count, 0)
        self.project.write(
            {
                "allow_worksheets": True,
                "allow_material": True,
                "allow_timesheets": True,
                "timesheet_product_id": self.product_service.id,
            }
        )
        self.assertEqual(self.task.display_enabled_conditions_count, 3)

        self.assertFalse(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertFalse(self.task.display_send_report_secondary)

        self.assertEqual(self.task.display_satisfied_conditions_count, 0)
        timesheet = self.env["account.analytic.line"].create(
            {
                "task_id": self.task.id,
                "project_id": self.project.id,
                "date": datetime.now(),
                "name": "My Timesheet",
                "user_id": self.env.uid,
                "unit_amount": 1,
            }
        )
        self.assertEqual(self.task.display_satisfied_conditions_count, 1)
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertTrue(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertTrue(self.task.display_send_report_secondary)
        timesheet.task_id = False

        self.assertEqual(self.task.display_satisfied_conditions_count, 0)
        worksheet_vals = {
            "x_name": "This is a name",
            "x_comments": "This is a comment",
            "x_project_task_id": self.task.id,
        }
        worksheet = self.env[self.task.worksheet_template_id.model_id.model].create(
            worksheet_vals
        )
        self.assertEqual(self.task.display_satisfied_conditions_count, 1)
        self.assertTrue(self.task.worksheet_count)
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertTrue(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertTrue(self.task.display_send_report_secondary)
        worksheet.unlink()

        self.assertEqual(self.task.display_satisfied_conditions_count, 0)
        self.task._fsm_get_or_create_sale_order()
        self.product_material.with_context(fsm_task_id=self.task.id).fsm_add_quantity()
        self.assertEqual(self.task.display_satisfied_conditions_count, 1)
        self.assertTrue(self.task.material_line_product_count)
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertTrue(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertTrue(self.task.display_send_report_secondary)

        timesheet.task_id = self.task
        self.assertEqual(self.task.display_satisfied_conditions_count, 2)
        worksheet = self.env[self.task.worksheet_template_id.model_id.model].create(
            worksheet_vals
        )
        self.assertEqual(self.task.display_satisfied_conditions_count, 3)
        self.assertTrue(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)
        self.assertTrue(
            self.task.display_send_report_primary
        )
        self.assertFalse(
            self.task.display_send_report_secondary
        )

        f = io.BytesIO()
        Image.new("RGB", (50, 50)).save(f, "PNG")
        f.seek(0)
        image = base64.b64encode(f.read())
        self.task.worksheet_signature = image
        self.assertTrue(
            self.task.display_send_report_primary
        )
        self.assertFalse(self.task.display_send_report_secondary)
        self.task.fsm_is_sent = True
        self.assertFalse(self.task.display_send_report_primary)
        self.assertFalse(
            self.task.display_send_report_secondary
        )

    def test_send_sign_report_button_02(self):
        f = io.BytesIO()
        Image.new("RGB", (50, 50)).save(f, "PNG")
        f.seek(0)
        image = base64.b64encode(f.read())
        self.task.worksheet_signature = image
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)

    def test_send_sign_report_button_03(self):
        self.project.allow_worksheets = False
        self.project.allow_material = False
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertFalse(self.task.display_send_report_secondary)

    def test_mark_as_done_01(self):
        self.assertFalse(self.task.display_mark_as_done_primary)
        self.assertTrue(self.task.display_mark_as_done_secondary)

        self.task.is_fsm = False
        self.assertFalse(self.task.display_mark_as_done_primary)
        self.assertFalse(self.task.display_mark_as_done_secondary)
        self.task.is_fsm = True
        self.task.fsm_done = True
        self.assertFalse(self.task.display_mark_as_done_primary)
        self.assertFalse(self.task.display_mark_as_done_secondary)
        self.task.fsm_done = False

        self.env["account.analytic.line"].create(
            {
                "task_id": self.task.id,
                "project_id": self.project.id,
                "date": datetime.now(),
                "name": "My Timesheet",
                "user_id": self.env.uid,
                "unit_amount": 1,
            }
        )
        self.assertFalse(self.task.display_mark_as_done_primary)
        self.assertTrue(self.task.display_mark_as_done_secondary)

        self.env[self.task.worksheet_template_id.model_id.model].create(
            {
                "x_name": "This is a name",
                "x_comments": "This is a comment",
                "x_project_task_id": self.task.id,
            }
        )
        self.task._fsm_get_or_create_sale_order()
        self.product_material.with_context(fsm_task_id=self.task.id).fsm_add_quantity()
        self.assertTrue(self.task.display_mark_as_done_primary)
        self.assertFalse(self.task.display_mark_as_done_secondary)

    def test_create_invoice_01(self):
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        self.task._fsm_get_or_create_sale_order()

        self.product_material.with_context(fsm_task_id=self.task.id).fsm_add_quantity()
        if self.task.sale_order_id.state != "done":
            self.task.sale_order_id.action_confirm()

        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        self.task.fsm_done = True
        self.assertEqual(self.task.sale_order_id.invoice_state, "to do")
        self.assertTrue(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        self.task.sale_order_id.action_cancel()
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)
        self.task.sale_order_id.action_draft()
        self.task.sale_order_id.action_confirm()

        self.project.allow_billable = False
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)
        self.project.allow_billable = True

        new_product = self.env["product.product"].create(
            {
                "name": "Invoice on delivery product",
                "sale_ok": True,
                "invoice_policy": "transferred",
                "service_type": "manual",
                "list_price": 90.0,
            }
        )
        new_line = self.env["sale.order.line"].create(
            {
                "order_id": self.task.sale_order_id.id,
                "product_id": new_product.id,
                "price_unit": 10,
                "product_qty": 1,
            }
        )
        invoice = self.task.sale_order_id._create_invoices()
        self.assertEqual(self.task.sale_order_id.invoice_state, "to do")
        self.assertEqual(self.task.sale_order_id.amount_taxexc_to_invoice, 0.0)
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        new_line.product_qty = 0
        self.assertEqual(self.task.sale_order_id.invoice_state, "draft")
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        invoice.action_post()
        self.assertEqual(self.task.sale_order_id.invoice_state, "done")
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

    def test_create_invoice_waits_for_something_to_invoice_after_a_down_payment(self):
        product_on_delivery = self.env["product.product"].create(
            {
                "name": "Invoice on delivery product",
                "sale_ok": True,
                "invoice_policy": "transferred",
                "service_type": "manual",
                "list_price": 90.0,
            }
        )
        self.task._fsm_get_or_create_sale_order()
        order = self.task.sale_order_id
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product_on_delivery.id,
                "price_unit": 90.0,
                "product_qty": 1,
            }
        )
        if order.state != "done":
            order.action_confirm()
        self.task.fsm_done = True
        down_payment_wizard = (
            self.env["wizard.sale.order.invoice"]
            .with_context(active_model="sale.order", active_ids=order.ids)
            .create({"advance_payment_method": "fixed", "fixed_amount": 30.0})
        )
        down_payment_wizard.create_invoices()
        order.invoice_ids.action_post()
        down_payment_line = order.line_ids.filtered(
            lambda sol: sol.is_downpayment and not sol.display_type
        )

        self.assertEqual(order.invoice_state, "to do")
        self.assertEqual(down_payment_line.invoice_state, "to do")
        self.assertEqual(line.invoice_state, "no")
        self.assertFalse(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)

        line.qty_transferred = 1

        self.assertTrue(self.task.display_create_invoice_primary)
        self.assertFalse(self.task.display_create_invoice_secondary)
        action = self.task.action_create_invoice()
        self.assertNotEqual(
            action["context"].get("default_advance_payment_method"), "percentage"
        )
        invoice = order._create_invoices(final=True)
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(
            invoice.invoice_line_ids.sale_line_ids, line | down_payment_line
        )

    def test_customer_preview_report_signed(self):
        self.assertFalse(self.task.show_customer_preview)
        f = io.BytesIO()
        Image.new("RGB", (50, 50)).save(f, "PNG")
        f.seek(0)
        image = base64.b64encode(f.read())
        self.task.worksheet_signature = image
        self.task._compute_show_customer_preview()
        self.assertTrue(
            self.task.show_customer_preview,
            "The Preview button should be visible as the report was signed",
        )

    def test_customer_preview_report_sent(self):
        self.assertFalse(self.task.show_customer_preview)
        self.task.fsm_is_sent = True
        self.task._compute_show_customer_preview()
        self.assertTrue(
            self.task.show_customer_preview,
            "The Preview button should be visible as the report was sent",
        )
