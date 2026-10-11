from odoo.tests.common import TransactionCase


class TestEmployeeReport(TransactionCase):
    def test_leadership_level(self):
        employee_1 = self.env["hr.employee"].create(
            {
                "name": "Employee 1",
            }
        )
        employee_2, employee_3, employee_4 = self.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {n}",
                    "parent_id": employee_1.id,
                }
                for n in range(2, 5)
            ]
        )
        employee_5 = self.env["hr.employee"].create(
            {
                "name": "Employee 5",
                "parent_id": employee_2.id,
            }
        )

        for employee, expected_leadership_level in [
            (employee_1, 2),
            (employee_2, 1),
            (employee_3, 0),
            (employee_5, 0),
        ]:
            report_record = self.env["esg.employee.report"].browse(employee.id)
            self.assertEqual(report_record.leadership_level, expected_leadership_level)

        employee_1.parent_id = employee_4.id
        self.env.cr.flush()
        self.env["esg.employee.report"]._invalidate_cache()
        self.env["hr.employee"]._invalidate_cache()
        for employee, expected_leadership_level in [
            (
                employee_1,
                2,
            ),
            (employee_4, 3),
        ]:
            report_record = self.env["esg.employee.report"].browse(employee.id)
            self.assertEqual(report_record.leadership_level, expected_leadership_level)

        employee_1.parent_id = employee_1.id
        employee_4.parent_id = employee_4.id
        self.env.cr.flush()
        self.env["esg.employee.report"]._invalidate_cache()
        self.env["hr.employee"]._invalidate_cache()
        for employee, expected_leadership_level in [
            (employee_1, 2),
            (
                employee_4,
                0,
            ),
        ]:
            report_record = self.env["esg.employee.report"].browse(employee.id)
            self.assertEqual(report_record.leadership_level, expected_leadership_level)
