from odoo.tests.common import TransactionCase


class TestGanttRowHelpers(TransactionCase):
    def test_format_date_range_single_day(self):
        rendered = self.env["hr.leave"].format_date_range_to_string(
            {"start_date": "07/24/2026"}
        )
        self.assertEqual(rendered, "on 07/24/2026")

    def test_format_date_range_multi_day(self):
        rendered = self.env["hr.leave"].format_date_range_to_string(
            {"start_date": "07/24/2026", "end_date": "07/28/2026"}
        )
        self.assertEqual(rendered, "from 07/24/2026 to 07/28/2026")

    def test_format_date_range_partial_day(self):
        rendered = self.env["hr.leave"].format_date_range_to_string(
            {
                "start_date": "07/24/2026",
                "start_time": "8:00 AM",
                "end_time": "12:00 PM",
            }
        )
        self.assertEqual(rendered, "on 07/24/2026 from 8:00 AM to 12:00 PM")
