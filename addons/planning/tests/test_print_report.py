from datetime import datetime
from urllib.parse import urlencode

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from .common import TestCommonPlanning


@tagged("post_install", "-at_install")
class TestPlanningPrintReport(HttpCase, TestCommonPlanning):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpEmployees()
        cls.env["planning.slot"].create(
            {
                "resource_id": cls.resource_bert.id,
                "start_datetime": datetime(2025, 5, 19, 8, 0),
                "end_datetime": datetime(2025, 5, 19, 16, 0),
            }
        )

    def _print_planning_url(self):
        action = (
            self.env["planning.slot"]
            .with_context(discard_logo_check=True)
            .action_print_plannings(
                date_start="2025-05-19 00:00:00",
                date_end="2025-05-25 23:59:59",
                group_bys=["resource_id"],
                domain=[
                    ("start_datetime", "<", "2025-05-26 00:00:00"),
                    ("end_datetime", ">", "2025-05-19 00:00:00"),
                ],
            )
        )
        self.assertTrue(
            action, "the week holds a shift, so there is a planning to print"
        )
        data = action["data"]
        shifts = [
            shift
            for groups in data["group_by_slots_per_day_per_week"].values()
            for _group, days in groups
            for day_shifts in days.values()
            for shift in day_shifts
        ]
        self.assertEqual(
            len(shifts), 1, "one shift in the week, so one block in the report"
        )
        self.assertLessEqual(
            len(shifts[0]["title"]),
            20,
            "this test only means something while the printed title fits on one line",
        )
        return "/report/html/planning.slot_report?" + urlencode(
            {"options": json_dumps(data)}
        )

    def test_single_line_shift_block_is_not_double_height(self):
        self.browser_js(
            self._print_planning_url(),
            """
            const block = document.querySelector(".shift-block");
            if (!block) {
                console.error("the printed planning drew no .shift-block");
            } else if (block.offsetHeight >= 30) {
                console.error(
                    `a single-line shift block is ${block.offsetHeight}px tall, ` +
                    `it should take little more than its one line of text`
                );
            } else {
                console.log("test successful");
            }
            """,
            login="admin",
        )
