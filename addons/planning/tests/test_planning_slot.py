from datetime import UTC, datetime, timedelta

from odoo.libs.datetime import timezone
from odoo.libs.intervals import Intervals
from odoo.tests import TransactionCase, new_test_user

from .common import TestPlanningContractCommon


class TestPlanningContract(TestPlanningContractCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_bert.version_id.write(
            {
                "contract_date_end": datetime.strptime("2015-11-15", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2015-01-01", "%Y-%m-%d"),
                "date_version": datetime.strptime("2015-01-01", "%Y-%m-%d"),
                "name": "First CDD Contract for Jules",
                "resource_calendar_id": cls.calendar_40h.id,
                "wage": 5000.0,
            }
        )
        cls.contract_cdd = cls.employee_bert.version_id

        cls.contract_cdi = cls.employee_bert.create_version(
            {
                "contract_date_start": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_end": False,
                "date_version": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "name": "Contract for Jules",
                "resource_calendar_id": cls.calendar_35h.id,
                "wage": 5000.0,
            }
        )

    def test_employee_contract_validity_per_period(self):
        start = datetime(2015, 11, 8, 00, 00, 00, tzinfo=UTC)
        end = datetime(2015, 11, 21, 23, 59, 59, tzinfo=UTC)
        calendars_validity_within_period = (
            self.resource_bert._get_calendars_validity_within_period(
                start, end, default_company=self.employee_bert.company_id
            )
        )
        tz = timezone(self.employee_bert.tz)

        self.assertEqual(
            len(calendars_validity_within_period[self.resource_bert.id]),
            2,
            "There should exist 2 calendars within the period",
        )
        interval_calendar_40h = Intervals(
            [
                (
                    start,
                    datetime.combine(
                        self.contract_cdd.date_end + timedelta(days=1),
                        datetime.min.time(),
                    ).replace(tzinfo=tz),
                    self.env["resource.calendar.attendance"],
                )
            ]
        )
        interval_calendar_35h = Intervals(
            [
                (
                    datetime.combine(
                        self.contract_cdi.date_start, datetime.min.time()
                    ).replace(tzinfo=tz),
                    end,
                    self.env["resource.calendar.attendance"],
                )
            ]
        )
        computed_interval_40h = calendars_validity_within_period[self.resource_bert.id][
            self.calendar_40h
        ]
        computed_interval_35h = calendars_validity_within_period[self.resource_bert.id][
            self.calendar_35h
        ]
        self.assertFalse(
            computed_interval_40h - interval_calendar_40h,
            "The interval of validity for the 40h calendar must be from 2015-11-16 to 2015-11-21, not more",
        )
        self.assertFalse(
            interval_calendar_40h - computed_interval_40h,
            "The interval of validity for the 40h calendar must be from 2015-11-16 to 2015-11-21, not less",
        )
        self.assertFalse(
            computed_interval_35h - interval_calendar_35h,
            "The interval of validity for the 35h calendar must be from 2015-11-08 to 2015-11-15, not more",
        )
        self.assertFalse(
            interval_calendar_35h - computed_interval_35h,
            "The interval of validity for the 35h calendar must be from 2015-11-08 to 2015-11-15, not less",
        )

    def test_employee_work_intervals(self):
        start = datetime(2015, 11, 8, 00, 00, 00, tzinfo=UTC)
        end = datetime(2015, 11, 21, 23, 59, 59, tzinfo=UTC)
        work_intervals, _ = self.resource_bert._get_valid_work_intervals(start, end)
        sum_work_intervals = sum(
            (stop - start).total_seconds() / 3600
            for start, stop, _resource in work_intervals[self.resource_bert.id]
        )
        self.assertEqual(
            75,
            sum_work_intervals,
            "Sum of the work intervals for the employee Jules should be 40h+35h = 75h",
        )

    def test_employee_work_planning_hours_info(self):
        planning_hours_info = self.env["planning.slot"]._gantt_progress_bar(
            "resource_id",
            self.resource_bert.ids,
            datetime(2015, 11, 8),
            datetime(2015, 11, 21, 23, 59, 59),
        )
        self.assertEqual(
            75,
            planning_hours_info[self.resource_bert.id]["max_value"],
            "Work hours for the employee Jules should be 40h+35h = 75h",
        )

    def test_creation_recurrencing_planning_without_employee_contract_access(self):
        planning_value = {
            "name": "Test planning",
            "start_datetime": datetime(2015, 11, 8, 00, 00, 00),
            "end_datetime": datetime(2015, 11, 21, 23, 59, 59),
            "resource_id": self.resource_bert.id,
            "repeat": True,
            "repeat_type": "count",
            "repeat_number": 2,
            "repeat_interval": 1,
            "repeat_unit": "month",
        }
        user_admin = new_test_user(
            self.env,
            "User Admin",
            groups="planning.group_planning_manager,hr.group_hr_manager,hr.group_hr_manager",
        )
        user_without_contract = new_test_user(
            self.env,
            "User Without Contract",
            groups="planning.group_planning_manager,hr.group_hr_manager",
        )
        user_without_employee = new_test_user(
            self.env, "User Without Employee", groups="planning.group_planning_manager"
        )
        self.env["planning.slot"].with_user(user_admin).create(planning_value)
        self.env.invalidate_all()
        self.env["planning.slot"].with_user(user_without_contract).create(
            planning_value
        )
        self.env.invalidate_all()
        self.env["planning.slot"].with_user(user_without_employee).create(
            planning_value
        )

    def test_allocated_hours_of_slot_with_flexible_contract(self):

        self.employee_joseph.version_id.write(
            {
                "contract_date_end": datetime.strptime("2015-12-16", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "date_version": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "name": "Fully flex contract for Joseph",
                "resource_calendar_id": False,
                "wage": 5000.0,
            }
        )

        slot_outside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 17, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 17, 12, 0, 0),
                "resource_id": self.resource_joseph.id,
            }
        )
        self.assertEqual(
            slot_outside.allocated_hours,
            0,
            "The allocated hours should be 0 for a slot outside the contract period of a fully flexible employee",
        )

        slot_inside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 16, 1, 0, 0),
                "end_datetime": datetime(2015, 12, 16, 12, 0, 0),
                "resource_id": self.resource_joseph.id,
            }
        )
        self.assertEqual(
            slot_inside.allocated_hours,
            11,
            "The allocated hours should equal the whole length of the slot inside the contract period of a fully flexible employee",
        )

        self.employee_janice.version_id.write(
            {
                "date_version": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_end": datetime.strptime("2015-12-16", "%Y-%m-%d"),
                "name": "Flex contract for Janice",
                "resource_calendar_id": self.calendar_30h_flex.id,
                "wage": 5000.0,
            }
        )

        slot_outside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 17, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 17, 12, 0, 0),
                "resource_id": self.resource_janice.id,
            }
        )
        self.assertEqual(
            slot_outside.allocated_hours,
            0,
            "The allocated hours should be 0 for a slot outside the contract period of a flexible employee",
        )

        slot_inside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 16, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 16, 14, 0, 0),
                "resource_id": self.resource_janice.id,
            }
        )
        self.assertEqual(
            slot_inside.allocated_hours,
            6,
            "The allocated hours should be 6 for a slot inside the contract period of a flexible employee",
        )

        self.employee_janice.create_version(
            {
                "date_version": datetime.strptime("2016-01-16", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2016-01-16", "%Y-%m-%d"),
                "contract_date_end": False,
                "name": "Flex contract for Janice with no end date",
                "resource_calendar_id": self.calendar_30h_flex.id,
                "wage": 5000.0,
            }
        )

        slot_inside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2016, 1, 16, 8, 0, 0),
                "end_datetime": datetime(2016, 1, 16, 14, 0, 0),
                "resource_id": self.resource_janice.id,
            }
        )
        self.assertEqual(
            slot_inside.allocated_hours,
            6,
            "The allocated hours should be 6 for a slot inside the contract period of a flexible employee with no end date",
        )

    def test_allocated_hours_of_slot_overlapping_with_contract_period(self):

        self.employee_joseph.version_id.write(
            {
                "date_version": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_end": datetime.strptime("2015-12-16", "%Y-%m-%d"),
                "name": "Fully flex contract for Joseph",
                "resource_calendar_id": False,
                "wage": 5000.0,
            }
        )

        slot_outside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 16, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 17, 12, 0, 0),
                "resource_id": self.resource_joseph.id,
            }
        )
        self.assertEqual(
            slot_outside.allocated_hours,
            16.0,
            "The allocated hours should be 16h (8AM to 12PM) of the 16th of December for the fully flexible employee",
        )

        self.employee_janice.version_id.write(
            {
                "date_version": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_start": datetime.strptime("2015-11-16", "%Y-%m-%d"),
                "contract_date_end": datetime.strptime("2015-12-16", "%Y-%m-%d"),
                "name": "Flex contract for Janice",
                "resource_calendar_id": self.calendar_30h_flex.id,
                "wage": 5000.0,
            }
        )

        slot_outside = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 16, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 17, 8, 0, 0),
                "resource_id": self.resource_janice.id,
            }
        )
        self.assertEqual(
            slot_outside.allocated_hours,
            6.0,
            "The allocated hours should be 6h (the max per day) for the flexible employee",
        )

    def test_allocated_hours_on_open_shift(self):
        slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2015, 12, 16, 8, 0, 0),
                "end_datetime": datetime(2015, 12, 17, 8, 0, 0),
            }
        )
        self.assertEqual(
            slot.allocated_hours,
            8,
            "The allocated hours should be computed without any issue",
        )


class TestFlexibleSlotsShareTheWeek(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 40h",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Flexy",
                "type": "material",
                "calendar_id": calendar.id,
                "tz": "UTC",
            }
        )
        cls.monday = datetime(2026, 6, 1)
        cls.wednesday = datetime(2026, 6, 3)

    def _slot(self, start, stop):
        return self.env["planning.slot"].create(
            {
                "resource_id": self.resource.id,
                "start_datetime": start,
                "end_datetime": stop,
            }
        )

    def _hours(self, *slots):
        self.env.flush_all()
        return [
            (slot.allocated_hours, sum(slot.reservation_ids.mapped("allocated_hours")))
            for slot in slots
        ]

    def test_a_slot_holds_what_its_reservation_holds(self):
        first = self._slot(self.monday, self.wednesday)
        later = self._slot(self.wednesday, self.wednesday + timedelta(days=7))
        self.assertEqual(self._hours(first, later), [(16.0, 16.0), (40.0, 40.0)])

    def test_an_earlier_slot_gives_its_hours_back(self):
        first = self._slot(self.monday, self.wednesday)
        later = self._slot(self.wednesday, self.wednesday + timedelta(days=7))
        first.end_datetime = self.monday + timedelta(days=1)
        self.assertEqual(self._hours(later), [(48.0, 48.0)])
        first.unlink()
        self.assertEqual(self._hours(later), [(56.0, 56.0)])

    def test_typed_hours_are_a_share_of_what_the_slot_can_hold(self):
        self._slot(self.monday, self.wednesday)
        later = self._slot(self.wednesday, self.wednesday + timedelta(days=7))
        later.allocated_hours = 20.0
        self.assertEqual(self._hours(later), [(20.0, 20.0)])
        self.assertAlmostEqual(later.allocated_percentage, 100 * 20 / 56, places=4)
