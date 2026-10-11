import datetime

from odoo.tests import freeze_time

from .test_common import TestCommon


@freeze_time("2020-01-01")
class TestSlotAbsenceSearch(TestCommon):
    """Cover the is_absent searcher on planning slots."""

    def test_search_is_absent(self):
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "holiday_status_id": self.leave_type.id,
                    "employee_id": self.employee_bert.id,
                    "request_date_from": "2020-01-02",
                    "request_date_to": "2020-01-02",
                }
            )
        )
        leave.action_approve()

        absent_slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime.datetime(2020, 1, 2, 8, 0),
                "end_datetime": datetime.datetime(2020, 1, 2, 17, 0),
            }
        )
        present_slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_joseph.id,
                "start_datetime": datetime.datetime(2020, 1, 2, 8, 0),
                "end_datetime": datetime.datetime(2020, 1, 2, 17, 0),
            }
        )

        found = self.env["planning.slot"].search([("is_absent", "=", True)])
        self.assertIn(absent_slot, found)
        self.assertNotIn(present_slot, found)

        not_absent = self.env["planning.slot"].search([("is_absent", "!=", True)])
        self.assertIn(present_slot, not_absent)
        self.assertNotIn(absent_slot, not_absent)
