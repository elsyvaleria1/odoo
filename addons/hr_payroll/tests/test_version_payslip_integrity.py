from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestVersionPayslipIntegrity(TestPayslipBase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.version = cls.richard_emp.create_version(
            {
                "date_version": date(2025, 1, 1),
                "wage": 4000.0,
            }
        )

    def _create_payslip(self):
        return self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.version.id,
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 1, 31),
            }
        )

    def test_archive_version_with_draft_payslip(self):
        self._create_payslip()
        self.version.action_archive()
        self.assertFalse(self.version.active)

    def test_archive_version_with_validated_payslip(self):
        payslip = self._create_payslip()
        payslip.action_validate()
        self.assertEqual(payslip.state, "validated")

        with self.assertRaises(ValidationError):
            self.version.action_archive()

        payslip.action_payslip_draft()
        self.version.action_archive()
        self.assertFalse(self.version.active)

    def test_unlink_version_with_validated_payslip(self):
        payslip = self._create_payslip()
        payslip.action_validate()

        with self.assertRaises(ValidationError):
            self.version.unlink()

    def test_validate_payslip_on_archived_version(self):
        payslip = self._create_payslip()
        self.version.action_archive()

        with self.assertRaises(ValidationError):
            payslip.action_validate()

        self.version.action_unarchive()
        payslip.action_validate()
        self.assertEqual(payslip.state, "validated")
