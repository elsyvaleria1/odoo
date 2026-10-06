from datetime import datetime

from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests.common import TransactionCase


class TestWorkEntryPayslipLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Locked employee",
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )
        cls.work_entry_type = cls.env["hr.work.entry.type"].create(
            {"name": "Payslip link test", "code": "PAYLINKTEST100"}
        )
        cls.work_entry = cls.env["hr.work.entry"].create(
            {
                "name": "Locked entry",
                "employee_id": cls.employee.id,
                "version_id": cls.employee.version_id.id,
                "work_entry_type_id": cls.work_entry_type.id,
                "date": Date.to_date("2025-03-03"),
                "duration": 8.0,
            }
        )
        cls.payslip = cls.env["hr.payslip"].create(
            {
                "name": "March payslip",
                "employee_id": cls.employee.id,
                "date_from": Date.to_date("2025-03-01"),
                "date_to": Date.to_date("2025-03-31"),
            }
        )
        cls.payslip.write(
            {"state": "validated", "done_date": datetime(2025, 4, 1, 8, 0)}
        )
        cls.work_entry.state = "validated"

    def test_action_view_payslip_opens_the_payslip_that_locked_the_entry(self):
        """A locked work entry should say which payslip locked it."""
        self.assertTrue(self.work_entry.has_payslip)
        action = self.work_entry.action_view_payslip()
        self.assertEqual(action["res_model"], "hr.payslip")
        self.assertEqual(action["res_id"], self.payslip.id)

    def test_action_view_payslip_ignores_a_refunded_payslip(self):
        """`has_payslip` discounts refunded payslips, so the button must too.

        Otherwise the entry reports no payslip and the action opens one anyway.
        """
        self.payslip.is_refunded = True
        self.work_entry.invalidate_recordset(["has_payslip"])
        self.assertFalse(self.work_entry.has_payslip)
        with self.assertRaises(UserError):
            self.work_entry.action_view_payslip()

    def test_gantt_popover_links_to_the_payslip(self):
        """The link has to survive view inheritance into the gantt popover arch."""
        arch = self.env["hr.work.entry"].get_view(
            self.env.ref("hr_work_entry_enterprise.hr_work_entry_gantt").id, "gantt"
        )["arch"]
        self.assertIn("action_view_payslip", arch)
        self.assertIn('name="has_payslip"', arch)
