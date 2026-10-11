from odoo.tests.common import TransactionCase, tagged

from odoo.addons.hr_timesheet.tools.time_units import hours_to_days


@tagged("post_install", "-at_install")
class TestTimesheetTimeUnits(TransactionCase):
    def test_display_rounding_and_negative_hours(self):
        for hours, expected in ((0, 0), (8, 1), (1, 0.13), (-1, -0.13), (20, 2.5)):
            with self.subTest(hours=hours):
                self.assertEqual(hours_to_days(self.env, hours), expected)
                for name in ("project.task", "account.analytic.line"):
                    self.assertEqual(
                        self.env[name]._convert_hours_to_days(hours), expected
                    )

    def test_conversion_uses_configured_day_length(self):
        self.env.ref("base.product_uom_day").relative_factor = 6
        for name in ("project.task", "account.analytic.line"):
            self.assertEqual(self.env[name]._convert_hours_to_days(9), 1.5)

    def test_keyword_and_recordset_contract(self):
        for name in ("project.task", "account.analytic.line"):
            records = self.env[name].browse([123456, 123457])
            self.assertEqual(records._convert_hours_to_days(time=16), 2)
