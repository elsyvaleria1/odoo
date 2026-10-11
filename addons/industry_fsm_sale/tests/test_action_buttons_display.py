import base64
import io
from datetime import datetime

from PIL import Image

from odoo.tests import TransactionCase


class TestActionButtons(TransactionCase):
    """Test visibility of the following buttons:
    - Send/Sign Report
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "worksheet_template_id" in cls.env["project.task"]._fields:
            cls.skipTest(
                cls,
                "`industry_fsm_report` module must not be installed to run the tests",
            )
        cls.customer = cls.env["res.partner"].create({"name": "My Customer"})
        cls.env.company.hr_timesheet_config_id.timesheet_encode_uom_id = cls.env.ref(
            "base.product_uom_hour"
        )
        cls.product_service = cls.env["product.product"].create(
            {
                "name": "My Service Product",
                "type": "service",
            }
        )
        cls.product_material = cls.env["product.product"].create(
            {
                "name": "My Material Product",
                "invoice_policy": "ordered",
                "service_type": "manual",
            }
        )
        cls.project = cls.env["project.project"].create(
            {
                "name": "My Project",
                "partner_id": cls.customer.id,
                "allow_timesheets": True,
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

    def test_send_sign_report_buttons_visibility_conditions(self):

        self.assertEqual(self.task.display_enabled_conditions_count, 2)

        self.project.allow_material = False
        self.assertFalse(self.task.display_sign_report_primary)
        self.assertFalse(self.task.display_sign_report_secondary)
        self.assertFalse(self.task.display_send_report_primary)
        self.assertFalse(self.task.display_send_report_secondary)
        self.assertEqual(self.task.display_enabled_conditions_count, 1)

        self.project.allow_timesheets = False
        self.assertEqual(self.task.display_enabled_conditions_count, 0)
        self.project.write(
            {
                "allow_material": True,
                "allow_timesheets": True,
                "timesheet_product_id": self.product_service.id,
            }
        )
        self.assertEqual(self.task.display_enabled_conditions_count, 2)

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
