from odoo.tests.common import TransactionCase


class TestHrAttendanceScenario(TransactionCase):

    def test_the_guard_declines_on_a_database_that_already_has_sample_data(self):
        attendance = self.env["hr.attendance"]
        if not attendance.has_demo_data():
            self.skipTest("this database carries no sample data")
        before = attendance.search_count([])
        self.assertIsNone(attendance._load_demo_data())
        self.assertEqual(
            attendance.search_count([]),
            before,
            "declining must create nothing at all, not part of the scenario",
        )

    def test_load_scenario(self):
        attendance = self.env["hr.attendance"]
        if attendance.has_demo_data():
            self.skipTest(
                "the scenario only loads on a database with no sample data; "
                "install with --without-demo=all to exercise it"
            )
        self.assertIsNotNone(attendance._load_demo_data())

        employees = self.env["hr.employee"].browse(
            [
                self.env.ref("hr.employee_sj").id,
                self.env.ref("hr.employee_mw").id,
                self.env.ref("hr.employee_eg").id,
            ]
        )
        for employee in employees:
            self.assertTrue(
                employee.attendance_ids,
                f"{employee.name} should have demo attendance records",
            )
