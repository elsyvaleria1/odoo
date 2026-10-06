from psycopg.errors import CheckViolation

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import TestPayslipBase


@tagged("payroll_version")
class TestVersion(TestPayslipBase):
    def test_hourly_wage_cannot_be_negative(self):
        """`hourly_wage` feeds `hr.payslip.worked_days.hourly_rate`, so a
        negative value silently produces negative worked days."""
        version = self.richard_emp.version_id
        with mute_logger("odoo.sql_db"), self.assertRaises(CheckViolation):
            version.hourly_wage = -1
            version.flush_recordset()

    def test_hourly_wage_can_be_zero(self):
        version = self.richard_emp.version_id
        version.hourly_wage = 0
        version.flush_recordset()
        self.assertEqual(version.hourly_wage, 0)
