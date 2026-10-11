import re
from ast import literal_eval
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from psycopg.errors import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, new_test_user
from odoo.tools import mute_logger

from .common import TestCommonPlanning
from odoo.addons.mail.tests.common import MockEmail


class TestPlanning(TestCommonPlanning, MockEmail):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(cls.env.cr, "now", datetime.now)
        with freeze_time("2019-05-01"):
            cls.setUpCalendars()
            cls.setUpEmployees()
        calendar_joseph = cls.env["resource.calendar"].create(
            {
                "name": "Calendar 1",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Morning",
                            "dayofweek": "3",
                            "hour_from": 9,
                            "hour_to": 13,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Lunch",
                            "dayofweek": "3",
                            "hour_from": 13,
                            "hour_to": 14,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Afternoon",
                            "dayofweek": "3",
                            "hour_from": 14,
                            "hour_to": 18,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )
        calendar_bert = cls.env["resource.calendar"].create(
            {
                "name": "Calendar 2",
                "tz": "UTC",
                "hours_per_day": 4,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Morning",
                            "dayofweek": "3",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "morning",
                        },
                    ),
                ],
            }
        )
        cls.env.user.company_id.resource_calendar_id = cls.company_calendar
        cls.employee_joseph.resource_calendar_id = calendar_joseph
        cls.employee_bert.resource_calendar_id = calendar_bert
        cls.slot, cls.slot2 = cls.env["planning.slot"].create(
            [
                {
                    "start_datetime": datetime(2019, 6, 27, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 27, 18, 0, 0),
                },
                {
                    "start_datetime": datetime(2019, 6, 27, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 28, 18, 0, 0),
                },
            ]
        )
        cls.template = cls.env["planning.slot.template"].create(
            {
                "start_time": 11,
                "end_time": 14,
                "duration_days": 1,
            }
        )

        cls.flex_role = cls.env["resource.role"].create({"name": "flex role"})
        cls.flex_employee = cls.env["hr.employee"].create(
            {
                "name": "Night employee",
                "resource_calendar_id": cls.flex_40h_calendar.id,
                "default_planning_role_id": cls.flex_role.id,
                "tz": "UTC",
            }
        )

    def test_allocated_hours_defaults(self):
        self.assertEqual(
            self.slot.allocated_hours,
            8,
            "It should follow the calendar of the resource to compute the allocated hours.",
        )
        self.assertEqual(
            self.slot.allocated_percentage, 100, "It should have the default value"
        )

    def test_change_percentage(self):
        self.slot.allocated_percentage = 60
        self.assertEqual(
            self.slot.allocated_hours, 8 * 0.60, "It should 60%% of working hours"
        )
        self.slot2.allocated_percentage = 60
        self.assertEqual(self.slot2.allocated_hours, 16 * 0.60)

    def test_change_hours_more(self):
        self.slot.allocated_hours = 12
        self.assertEqual(self.slot.allocated_percentage, 150)
        self.slot2.allocated_hours = 24
        self.assertEqual(self.slot2.allocated_percentage, 150)

    def test_change_hours_less(self):
        self.slot.allocated_hours = 4
        self.assertEqual(self.slot.allocated_percentage, 50)
        self.slot2.allocated_hours = 8
        self.assertEqual(self.slot2.allocated_percentage, 50)

    def test_change_start(self):
        self.slot.start_datetime += relativedelta(hours=2)
        self.assertEqual(self.slot.allocated_percentage, 100, "It should still be 100%")
        self.assertEqual(self.slot.allocated_hours, 8, "It should decreased by 2 hours")

    def test_change_start_partial(self):
        self.slot.allocated_percentage = 80
        self.slot.start_datetime += relativedelta(hours=2)
        self.slot.flush_recordset()
        self.slot.invalidate_recordset()
        self.assertEqual(
            self.slot.allocated_hours,
            8 * 0.8,
            "It should be decreased by 2 hours and percentage applied",
        )
        self.assertEqual(self.slot.allocated_percentage, 80, "It should still be 80%")

    def test_change_end(self):
        self.slot.end_datetime -= relativedelta(hours=2)
        self.assertEqual(self.slot.allocated_percentage, 100, "It should still be 100%")
        self.assertEqual(self.slot.allocated_hours, 8, "It should decreased by 2 hours")

    def test_set_template(self):
        self.env.user.tz = "Europe/Brussels"
        self.slot.template_id = self.template
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 9, 0),
            "It should set time from template, in user timezone (11am CET -> 9am UTC)",
        )

    def test_change_employee_with_template(self):
        self.env.user.tz = "UTC"
        self.slot.template_id = self.template
        self.env.flush_all()

        self.env.user.tz = False
        self.slot.resource_id = self.employee_janice.resource_id
        self.assertEqual(
            self.slot.template_id, self.template, "It should keep the template"
        )
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 15, 0),
            "It should adjust for employee timezone: 11am EDT -> 3pm UTC",
        )

    def test_change_employee(self):
        self.env.user.tz = "UTC"
        self.slot.resource_id = self.employee_joseph.resource_id
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 8, 0),
            "It should not adjust to employee calendar",
        )
        self.assertEqual(
            self.slot.end_datetime,
            datetime(2019, 6, 27, 18, 0),
            "It should not adjust to employee calendar",
        )
        self.slot.resource_id = self.employee_bert.resource_id
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 8, 0),
            "It should not adjust to employee calendar",
        )
        self.assertEqual(
            self.slot.end_datetime,
            datetime(2019, 6, 27, 18, 0),
            "It should not adjust to employee calendar",
        )

    def test_create_with_employee(self):
        self.env.user.tz = "UTC"
        PlanningSlot = self.env["planning.slot"].with_context(
            tz="UTC",
            default_start_datetime="2019-06-27 00:00:00",
            default_end_datetime="2019-06-27 23:59:59",
            default_resource_id=self.resource_joseph.id,
        )
        defaults = PlanningSlot.default_get(
            ["resource_id", "start_datetime", "end_datetime"]
        )
        self.assertEqual(
            defaults.get("start_datetime"),
            datetime(2019, 6, 27, 9, 0),
            "It should be adjusted to employee calendar: 0am -> 9pm",
        )
        self.assertEqual(
            defaults.get("end_datetime"),
            datetime(2019, 6, 27, 18, 0),
            "It should be adjusted to employee calendar: 0am -> 18pm",
        )

    def test_specific_time_creation(self):
        self.env.user.tz = "UTC"
        PlanningSlot = self.env["planning.slot"].with_context(
            tz="UTC",
            default_start_datetime="2020-10-05 06:00:00",
            default_end_datetime="2020-10-05 12:30:00",
            planning_keep_default_datetime=True,
        )
        defaults = PlanningSlot.default_get(["start_datetime", "end_datetime"])
        self.assertEqual(
            defaults.get("start_datetime"),
            datetime(2020, 10, 5, 6, 0),
            "start_datetime should not change",
        )
        self.assertEqual(
            defaults.get("end_datetime"),
            datetime(2020, 10, 5, 12, 30),
            "end_datetime should not change",
        )

    def test_create_with_employee_outside_schedule(self):
        self.env.user.tz = "UTC"
        PlanningSlot = self.env["planning.slot"].with_context(
            tz="UTC",
            default_start_datetime="2019-06-26 00:00:00",
            default_end_datetime="2019-06-26 23:59:59",
            default_resource_id=self.resource_joseph.id,
        )
        defaults = PlanningSlot.default_get(
            ["resource_id", "start_datetime", "end_datetime"]
        )
        self.assertEqual(
            defaults.get("start_datetime"),
            datetime(2019, 6, 26, 8, 0),
            "It should adjust to employee calendar: 0am -> 8pm",
        )
        self.assertEqual(
            defaults.get("end_datetime"),
            datetime(2019, 6, 26, 17, 0),
            "It should adjust to employee calendar: 0am -> 5am",
        )

        PlanningSlot = self.env["planning.slot"].with_context(
            tz="UTC",
            default_start_datetime="2019-12-07 00:00:00",
            default_end_datetime="2019-12-08 23:59:59",
        )
        defaults = PlanningSlot.default_get(
            ["resource_id", "start_datetime", "end_datetime"]
        )

        self.assertEqual(
            defaults.get("start_datetime"),
            datetime(2019, 12, 7, 8, 0),
            "The start time should be adjusted to the default working hours: 8:00 AM on non-working days",
        )
        self.assertEqual(
            defaults.get("end_datetime"),
            datetime(2019, 12, 8, 17, 0),
            "The end date should be adjusted to the default working hours: 17:00 on on non-working days",
        )

    def test_create_without_employee(self):
        self.env.user.tz = "UTC"
        PlanningSlot = self.env["planning.slot"].with_context(
            tz="UTC",
            default_start_datetime="2019-06-27 00:00:00",
            default_end_datetime="2019-06-27 23:59:59",
            default_resource_id=False,
        )
        defaults = PlanningSlot.default_get(
            ["resource_id", "start_datetime", "end_datetime"]
        )
        self.assertEqual(
            defaults.get("start_datetime"),
            datetime(2019, 6, 27, 6, 0),
            "It should adjust to employee calendar: 0am -> 6pm",
        )
        self.assertEqual(
            defaults.get("end_datetime"),
            datetime(2019, 6, 27, 15, 0),
            "It should adjust to employee calendar: 0am -> 3pm",
        )

    def test_unassign_employee_with_template(self):
        self.env.user.tz = "America/New_York"
        self.env.user.company_id.resource_calendar_id.tz = "America/New_York"
        self.slot.template_id = self.template
        self.env.flush_all()
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 15, 0),
            "It should set time from template, in user timezone (11am EDT -> 3pm UTC)",
        )

        self.env.user.tz = False
        self.slot.resource_id = self.resource_janice.id
        self.env.flush_all()
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 15, 0),
            "It should adjust to employee timezone",
        )

        self.slot.resource_id = None
        self.assertEqual(
            self.slot.template_id, self.template, "It should keep the template"
        )
        self.assertEqual(
            self.slot.start_datetime,
            datetime(2019, 6, 27, 15, 0),
            "It should reset to company calendar timezone: 11am EDT -> 3pm UTC",
        )

    def test_compute_overlap_count(self):
        self.slot_6_2 = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2019, 6, 2, 8, 0),
                "end_datetime": datetime(2019, 6, 2, 17, 0),
            }
        )
        self.slot_6_3 = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2019, 6, 3, 8, 0),
                "end_datetime": datetime(2019, 6, 3, 17, 0),
            }
        )
        self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2019, 6, 2, 10, 0),
                "end_datetime": datetime(2019, 6, 2, 12, 0),
            }
        )
        self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2019, 6, 2, 16, 0),
                "end_datetime": datetime(2019, 6, 2, 18, 0),
            }
        )
        self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2019, 6, 2, 18, 0),
                "end_datetime": datetime(2019, 6, 2, 20, 0),
            }
        )
        self.assertEqual(2, self.slot_6_2.overlap_slot_count, "2 slots overlap")
        self.assertEqual(0, self.slot_6_3.overlap_slot_count, "no slot overlap")

    def test_compute_datetime_with_template_slot(self):
        self.employee_bert.resource_calendar_id = self.company_calendar
        template_slot = self.env["planning.slot.template"].create(
            {
                "start_time": 11,
                "end_time": 14,
                "duration_days": 2,
            }
        )

        slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2021, 1, 4, 0, 0),
                "end_datetime": datetime(2021, 1, 4, 23, 59),
                "resource_id": self.resource_bert.id,
            }
        )

        slot.write(
            {
                "template_id": template_slot.id,
            }
        )

        self.assertEqual(
            slot.start_datetime,
            datetime(2021, 1, 4, 11, 0),
            "The start datetime should have the same hour and minutes defined in the template in the resource timezone.",
        )
        self.assertEqual(
            slot.end_datetime,
            datetime(2021, 1, 5, 14, 0),
            "The end datetime of this slot should be 3 hours after the start datetime as mentionned in the template in the resource timezone.",
        )
        self.assertEqual(
            slot.allocated_hours,
            10,
            "The allocated hours of this slot should be the duration defined in the template in the resource timezone.",
        )

    def test_planning_state(self):
        self.slot.resource_id = self.employee_bert.resource_id
        self.assertEqual(self.slot.state, "1_draft", "Planning is draft mode.")
        self.slot.action_send()
        self.assertEqual(self.slot.state, "2_published", "Planning is published.")

    def test_create_working_calendar_period(self):
        test = Form(
            self.env["planning.slot"].with_context(
                default_start_datetime=datetime(2019, 5, 27, 0, 0),
                default_end_datetime=datetime(2019, 5, 27, 23, 59, 59),
            )
        )
        slot = test.save()
        self.assertEqual(
            slot.start_datetime,
            datetime(2019, 5, 27, 8, 0),
            "It should adjust to employee calendar: 0am -> 9pm",
        )
        self.assertEqual(
            slot.end_datetime,
            datetime(2019, 5, 27, 17, 0),
            "It should adjust to employee calendar: 0am -> 9pm",
        )

        test_week = Form(
            self.env["planning.slot"].with_context(
                default_start_datetime=datetime(2019, 6, 23, 0, 0),
                default_end_datetime=datetime(2019, 6, 29, 23, 59, 59),
            )
        )

        test_week = test_week.save()
        self.assertEqual(
            test_week.start_datetime,
            datetime(2019, 6, 24, 8, 0),
            "It should adjust to employee calendar: 0am -> 9pm",
        )
        self.assertEqual(
            test_week.end_datetime,
            datetime(2019, 6, 28, 17, 0),
            "It should adjust to employee calendar: 0am -> 9pm",
        )

    def test_create_planing_slot_without_start_date(self):
        planning_role = self.env["resource.role"].create({"name": "role x"})
        template = self.env["planning.slot.template"].create(
            {
                "start_time": 10,
                "end_time": 15,
                "duration_days": 1,
                "role_id": planning_role.id,
            }
        )
        with Form(self.env["planning.slot"]) as slot_form:
            slot_form.template_id = template
            slot_form.start_datetime = False
            slot_form.template_id = self.template
            self.assertEqual(slot_form.template_id, self.template)

    def test_shift_switching(self):
        bert_user = new_test_user(
            self.env,
            login="bert_user",
            groups="planning.group_planning_user",
            name="Bert User",
            email="user@example.com",
        )
        self.employee_bert.user_id = bert_user.id
        joseph_user = new_test_user(
            self.env,
            login="joseph_user",
            groups="planning.group_planning_user",
            name="Joseph User",
            email="juser@example.com",
        )
        self.employee_joseph.user_id = joseph_user.id

        self.slot.resource_id = self.employee_bert.resource_id
        self.assertEqual(
            self.slot.is_past, True, "The shift for this test should be in the past"
        )
        with self.assertRaises(UserError):
            self.slot.with_user(bert_user).action_switch_shift()

        self.assertEqual(
            self.slot.resource_id,
            self.employee_bert.resource_id,
            "The shift should be assigned to Bert",
        )
        with self.assertRaises(UserError):
            self.slot.with_user(joseph_user).action_switch_shift()

        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime.now() + relativedelta(days=2),
                "end_datetime": datetime.now() + relativedelta(days=4),
                "state": "2_published",
                "employee_id": bert_user.employee_id.id,
                "resource_id": self.employee_bert.resource_id.id,
            }
        )

        with self.mock_mail_gateway():
            self.assertEqual(
                test_slot.request_to_switch,
                False,
                "Before requesting to switch, the request to switch should be False",
            )
            test_slot.with_user(bert_user).action_switch_shift()
            self.assertEqual(
                test_slot.request_to_switch,
                True,
                "After the switch action, the request to switch should be True",
            )

            test_slot.with_user(joseph_user).action_self_assign()
            self.assertEqual(
                test_slot.request_to_switch,
                False,
                "After the assign action, the request to switch should be False",
            )
            self.assertEqual(
                test_slot.resource_id,
                self.employee_joseph.resource_id,
                "The shift should now be assigned to Joseph",
            )

            test_slot.with_user(joseph_user).action_switch_shift()
            self.assertEqual(
                test_slot.request_to_switch,
                True,
                "After the switch action, the request to switch should be True",
            )
            test_slot.write(
                {
                    "start_datetime": (datetime.now() + relativedelta(days=3)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                }
            )
            self.assertEqual(
                test_slot.request_to_switch,
                False,
                "After the change, the request to switch should be False",
            )

        self.assertEqual(len(self._new_mails), 1)
        self.assertMailMailWEmails(
            [bert_user.partner_id.email],
            None,
            author=joseph_user.partner_id,
        )

    @freeze_time("2023-11-20")
    def test_shift_creation_from_role(self):
        self.env.user.tz = "Asia/Kolkata"
        self.env.user.company_id.resource_calendar_id.tz = "Asia/Kolkata"
        PlanningRole = self.env["resource.role"]
        PlanningTemplate = self.env["planning.slot.template"]

        role_a = PlanningRole.create({"name": "role a"})
        role_b = PlanningRole.create({"name": "role b"})

        template_a = PlanningTemplate.create(
            {"start_time": 8, "end_time": 10, "duration_days": 1, "role_id": role_a.id}
        )
        self.assertEqual(
            template_a.duration_days,
            1,
            "Duration in days should be a 1 day according to resource calendar.",
        )
        self.assertEqual(
            template_a.end_time, 10.0, "End time should be 2 hours from start hours."
        )

        template_b = PlanningTemplate.create(
            {"start_time": 8, "end_time": 12, "duration_days": 1, "role_id": role_b.id}
        )

        slot = self.env["planning.slot"].create({"template_id": template_a.id})
        self.assertEqual(
            slot.role_id.id,
            slot.template_autocomplete_ids.mapped("role_id").id,
            "Role of the slot and shift template should be same.",
        )

        slot.template_id = template_b.id
        self.assertEqual(
            slot.role_id.id,
            slot.template_autocomplete_ids.mapped("role_id").id,
            "Role of the slot and shift template should be same.",
        )

    def test_manage_archived_resources(self):
        with freeze_time("2020-04-22"):
            self.env.user.tz = "UTC"
            slot_1, slot_2, slot_3 = self.env["planning.slot"].create(
                [
                    {
                        "resource_id": self.resource_bert.id,
                        "start_datetime": datetime(2020, 4, 20, 8, 0),
                        "end_datetime": datetime(2020, 4, 24, 17, 0),
                    },
                    {
                        "resource_id": self.resource_bert.id,
                        "start_datetime": datetime(2020, 4, 20, 8, 0),
                        "end_datetime": datetime(2020, 4, 21, 17, 0),
                    },
                    {
                        "resource_id": self.resource_bert.id,
                        "start_datetime": datetime(2020, 4, 23, 8, 0),
                        "end_datetime": datetime(2020, 4, 24, 17, 0),
                    },
                ]
            )

            slot1_initial_end_date = slot_1.end_datetime
            slot2_initial_end_date = slot_2.end_datetime

            self.resource_bert.employee_id.action_archive()

            self.assertEqual(
                slot_1.end_datetime,
                datetime.combine(fields.Date.today() + timedelta(days=1), time.min),
                "End date of the splited shift should be today",
            )
            self.assertNotEqual(
                slot_1.end_datetime,
                slot1_initial_end_date,
                "End date should be updated",
            )
            self.assertEqual(
                slot_2.end_datetime,
                slot2_initial_end_date,
                "End date should be the same",
            )
            self.assertFalse(
                slot_3.resource_id,
                "Resource should be the False for archeived resource shifts",
            )

    def test_avoid_rounding_error_when_creating_template(self):
        template = self.env["planning.slot.template"].create(
            {
                "start_time": 8,
                "end_time": 13.1,
                "duration_days": 1,
            }
        )
        slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2021, 1, 1, 0, 0),
                "end_datetime": datetime(2021, 1, 1, 23, 59),
            }
        )
        slot.write(
            {
                "template_id": template.id,
            }
        )
        self.assertEqual(
            slot.end_datetime.minute,
            6,
            "The min should be 6, just like in the template, not 5 due to rounding error",
        )

    def test_end_time_rounding_edge_case(self):
        shift_template = self.env["planning.slot.template"].create(
            {
                "start_time": 8.995,
                "end_time": 17.996,
                "duration_days": 1,
            }
        )
        self.assertEqual(re.sub(r"\s+", " ", shift_template.name), "8:59 - 17:59")

    def test_copy_planning_shift(self):
        self.env.user.tz = "UTC"
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2020, 4, 20, 8, 0),
                "end_datetime": datetime(2020, 4, 24, 17, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(
            slot.state, "2_published", "The state of the shift should be published"
        )

        slot1 = slot.with_context(planning_split_tool=True).copy()
        self.assertEqual(
            slot1.state, "2_published", "The state of the shift should be copied"
        )

        slot2 = slot.with_context(planning_split_tool=False).copy()
        self.assertEqual(
            slot2.state, "1_draft", "The state of the shift should not be copied"
        )

        slot3 = slot.copy()
        self.assertEqual(
            slot3.state, "1_draft", "The state of the shift should not be copied"
        )

    def test_calculate_slot_duration_flexible_hours(self):

        employee = self.env["hr.employee"].create(
            {
                "name": "Test Employee",
                "tz": "UTC",
            }
        )
        employee.resource_id.calendar_id = self.flex_40h_calendar

        planning_slot_1 = self.env["planning.slot"].create(
            {
                "resource_id": employee.resource_id.id,
                "start_datetime": datetime(2024, 2, 23, 6, 0, 0),
                "end_datetime": datetime(2024, 2, 29, 6, 0, 0),
            }
        )
        self.assertEqual(
            planning_slot_1.allocated_hours,
            54.0,
            "day 23, 24 and 25 belong to week 8 (8*3 = 24h) / day 26, 27, 28 (8*3 = 24h) and 29 (6 hours from 0h to 6h) belong to week 9",
        )

        planning_slot_2 = self.env["planning.slot"].create(
            {
                "resource_id": employee.resource_id.id,
                "start_datetime": datetime(2024, 2, 18, 8, 0, 0),
                "end_datetime": datetime(2024, 2, 24, 16, 0, 0),
            }
        )
        self.assertEqual(
            planning_slot_2.allocated_hours,
            48.0,
            "Sun 18/02 is ISO week 7 (8h); Mon 19/02 -> Sat 24/02 is week 8, capped at the 40h weekly limit",
        )

    def test_auto_plan_employee_with_break_company_no_breaks(self):
        calendar_24hr = self.env["resource.calendar"].create(
            {
                "name": "24/24 Company Calendar",
                "tz": "UTC",
                "hours_per_day": 24.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Morning " + str(day),
                            "dayofweek": str(day),
                            "hour_from": 0,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    )
                    for day in range(7)
                ]
                + [
                    (
                        0,
                        0,
                        {
                            "name": "Afternoon " + str(day),
                            "dayofweek": str(day),
                            "hour_from": 12,
                            "hour_to": 24,
                            "day_period": "afternoon",
                        },
                    )
                    for day in range(7)
                ],
            }
        )
        self.env.user.company_id.resource_calendar_id = calendar_24hr

        night_shifts_calendar = self.env["resource.calendar"].create(
            {
                "name": "Night Shifts Calendar",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Afternoon " + str(day),
                            "dayofweek": str(day),
                            "hour_from": 21.5,
                            "hour_to": 24,
                            "day_period": "afternoon",
                        },
                    )
                    for day in range(7)
                ]
                + [
                    (
                        0,
                        0,
                        {
                            "name": "Break " + str(day),
                            "dayofweek": str(day),
                            "hour_from": 0,
                            "hour_to": 0.5,
                            "day_period": "lunch",
                        },
                    )
                    for day in range(7)
                ]
                + [
                    (
                        0,
                        0,
                        {
                            "name": "morning " + str(day),
                            "dayofweek": str(day),
                            "hour_from": 0.5,
                            "hour_to": 6,
                            "day_period": "morning",
                        },
                    )
                    for day in range(7)
                ],
            }
        )
        role = self.env["resource.role"].create({"name": "test role"})
        night_employee = self.env["hr.employee"].create(
            {
                "name": "Night employee",
                "resource_calendar_id": night_shifts_calendar.id,
                "default_planning_role_id": role.id,
            }
        )

        night_shift = self.env["planning.slot"].create(
            {
                "name": "Night Shift",
                "start_datetime": datetime(2024, 5, 10, 21, 30),
                "end_datetime": datetime(2024, 5, 11, 6, 0),
                "role_id": role.id,
            }
        )
        night_shift.allocated_hours = 8
        night_shift.auto_plan_id()

        self.assertEqual(
            night_shift.resource_id,
            night_employee.resource_id,
            "The night shift should be assigned to the night employee",
        )
        self.assertEqual(
            night_shift.allocated_hours, 8, "The allocated hours should remain the same"
        )
        self.assertEqual(
            night_shift.allocated_percentage,
            100,
            "The allocated percentage should be 100% as the resource will work the allocated hours",
        )

    def test_write_multiple_slots(self):
        slots = self.env["planning.slot"].create(
            [
                {
                    "start_datetime": datetime(2024, 5, 10, 8, 0),
                    "end_datetime": datetime(2024, 5, 10, 17, 0),
                },
                {
                    "start_datetime": datetime(2024, 6, 10, 8, 0),
                    "end_datetime": datetime(2024, 6, 10, 17, 0),
                },
            ]
        )
        slots.write({"resource_id": self.resource_bert.id})
        self.assertEqual(slots.resource_id, self.resource_bert)

    def test_write_without_resource(self):
        slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2024, 5, 10, 8, 0),
                "end_datetime": datetime(2024, 5, 10, 17, 0),
            }
        )
        slot.write(
            {
                "repeat": True,
                "recurrence_update": "all",
                "start_datetime": datetime(2024, 5, 10, 9, 0),
                "end_datetime": datetime(2024, 5, 10, 18, 0),
            }
        )
        self.assertRecordValues(
            slot,
            [
                {
                    "repeat": True,
                    "start_datetime": datetime(2024, 5, 10, 9, 0),
                    "end_datetime": datetime(2024, 5, 10, 18, 0),
                }
            ],
        )

    def test_compute_company_planning_slot(self):
        self.assertEqual(
            self.slot.company_id,
            self.env.company,
            "The slot's company should be the current one.",
        )
        company = self.env["res.company"].create({"name": "Test company"})
        self.resource_bert.company_id = company.id
        self.slot.resource_id = self.resource_bert.id
        self.assertEqual(
            self.slot.company_id,
            company,
            "The slot's company should be the resource's one.",
        )

    def test_flexible_contract_slot(self):
        self.employee_bert.resource_calendar_id = self.flex_50h_calendar
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2022, 1, 11, 3, 0),
                "end_datetime": datetime(2022, 1, 11, 23, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(
            slot.allocated_hours, 10.0, "The allocated hours should be 10.0"
        )
        self.assertEqual(
            slot.allocated_percentage, 100, "The allocated percentage should be 100%%"
        )

        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2022, 1, 12, 22, 0),
                "end_datetime": datetime(2022, 1, 13, 4, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(slot.allocated_hours, 6.0, "The allocated hours should be 6.0")
        self.assertEqual(
            slot.allocated_percentage, 100, "The allocated percentage should be 100%%"
        )

        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2022, 1, 13, 20, 0),
                "end_datetime": datetime(2022, 1, 14, 10, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(
            slot.allocated_hours,
            14.0,
            "4 hours available on day 13, 10 hours available on day 14, no daily limit excedded in both days",
        )
        self.assertEqual(
            slot.allocated_percentage, 100, "The allocated percentage should be 100%%"
        )

        slot.allocated_percentage = 50
        self.assertEqual(
            slot.allocated_hours,
            7.0,
            "The allocated hours should be 5.0 after changing the allocated percentage to 50%%",
        )

    def test_fully_flexible_contract_slot(self):
        self.employee_bert.resource_calendar_id = False
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2022, 1, 11, 4, 0),
                "end_datetime": datetime(2022, 1, 12, 22, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(
            slot.allocated_hours, 42.0, "The allocated hours should be 42.0"
        )
        self.assertEqual(
            slot.allocated_percentage, 100, "The allocated percentage should be 100%%"
        )

        slot.allocated_percentage = 50
        self.assertEqual(
            slot.allocated_hours,
            21.0,
            "The allocated hours should be 21.0 after changing the allocated percentage to 50%%",
        )

    def test_open_shift_planning_slot_including_weekend(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": False,
                "start_datetime": datetime(2022, 1, 16, 8, 0),
                "end_datetime": datetime(2022, 1, 17, 17, 0),
                "state": "2_published",
            }
        )
        self.assertEqual(
            slot.allocated_hours,
            16.0,
            "The allocated hours should be 16.0 for the open shift",
        )
        self.assertEqual(
            slot.allocated_percentage, 100, "The allocated percentage should be 100%%"
        )

    @freeze_time("2021-01-01")
    def test_allocated_hours_when_template_is_during_a_break(self):
        self.resource_janice.tz = "UTC"
        template_slot = self.env["planning.slot.template"].create(
            {
                "start_time": 11,
                "end_time": 16,
            }
        )

        slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2021, 1, 1, 0, 0),
                "end_datetime": datetime(2021, 1, 1, 23, 59),
                "resource_id": self.resource_janice.id,
            }
        )

        slot.write(
            {
                "template_id": template_slot.id,
            }
        )

        self.assertEqual(slot.start_datetime, datetime(2021, 1, 1, 11, 0))
        self.assertEqual(slot.end_datetime, datetime(2021, 1, 1, 16, 0))
        self.assertEqual(slot.allocated_hours, 4)

    def test_allocated_hours_shift_duplication(self):
        self.slot.resource_id = self.resource_joseph
        self.assertEqual(self.slot.allocated_hours, 8)
        slot2 = self.slot.copy({"resource_id": self.resource_bert.id})
        self.assertEqual(
            slot2.allocated_hours,
            4,
            "The allocated hours should have been recomputed with the new resource after copying the shift.",
        )

    def test_planning_expand_resource(self):
        self.employee_bert.resource_calendar_id = self.flex_50h_calendar
        self.slot.resource_id = self.employee_bert.resource_id
        group_by = ["resource_id"]

        planned_dates = [
            ("2019-07-01 00:00:00", "2019-07-31 23:59:59"),
            ("2019-08-01 00:00:00", "2019-08-31 23:59:59"),
        ]
        for case, (start_date, stop_date) in enumerate(planned_dates):
            result = (
                self.env["planning.slot"]
                .with_context(planning_expand_resource=True)
                .get_gantt_data(
                    [
                        "&",
                        ["start_datetime", "<", stop_date],
                        ["end_datetime", ">", start_date],
                    ],
                    group_by,
                    {"display_name": {}},
                    unavailability_fields=group_by,
                    progress_bar_fields=group_by,
                    start_date=start_date,
                    stop_date=stop_date,
                    scale="month",
                )
            )

            if case == 0:
                self.assertTrue(
                    self.slot.resource_id.id in result["progress_bars"]["resource_id"],
                    "Resource has slots in the previous month",
                )
                self.assertEqual(
                    result["progress_bars"]["resource_id"][self.slot.resource_id.id][
                        "value"
                    ],
                    0.0,
                )
            else:
                self.assertFalse(
                    self.slot.resource_id.id in result["progress_bars"]["resource_id"]
                )

    def test_allocated_hours_open_shift(self):
        self.employee_joseph.user_id = self.env.user.id
        PlanningSlot = self.env["planning.slot"]

        slot = PlanningSlot.create(
            {
                "start_datetime": datetime(2019, 5, 1, 8, 0),
                "end_datetime": datetime(2019, 5, 1, 17, 0),
            }
        )
        self.assertEqual(
            slot.allocated_hours,
            8.0,
            "The allocated hours should be 8.0 for the open shift based on the company calendar",
        )

        slot = PlanningSlot.create(
            {
                "start_datetime": datetime(2019, 5, 2, 8, 0),
                "end_datetime": datetime(2019, 5, 2, 17, 0),
            }
        )
        self.assertEqual(
            slot.allocated_hours,
            8.0,
            "The allocated hours should be 8.0 for the open shift based on the company calendar",
        )

    def test_planning_slot_default_datetime(self):
        self.resource_joseph.tz = "Europe/Brussels"
        PlanningSlot = (
            self.env["planning.slot"]
            .with_user(self.env.user)
            .with_context(
                default_start_datetime="2024-07-04 12:00:00",
                default_end_datetime="2024-07-04 12:59:59",
                default_resource_id=self.resource_joseph.id,
            )
        )
        slot = PlanningSlot.default_get(
            ["resource_id", "start_datetime", "end_datetime"]
        )
        self.assertEqual(
            slot.get("start_datetime"),
            datetime(2024, 7, 4, 10, 0, 0),
            "The slot start datetime should be matched to the resource's timezone",
        )
        self.assertEqual(
            slot.get("end_datetime"),
            datetime(2024, 7, 4, 10, 59, 59),
            "The slot end datetime should be matched to the resource's timezone",
        )

    def test_copy_shift_without_archive_resource(self):
        self.slot.resource_id = self.resource_joseph
        self.slot2.resource_id = self.resource_bert
        self.resource_joseph.action_archive()
        slots = self.slot + self.slot2
        slot, slot2 = slots.copy()
        self.assertFalse(slot.resource_id)
        self.assertEqual(slot2.resource_id, self.resource_bert)

        slot, slot2 = slots.copy({"resource_id": self.resource_joseph.id})
        self.assertEqual(slot.resource_id, self.resource_joseph)
        self.assertEqual(slot2.resource_id, self.resource_joseph)

        slot = self.slot.with_context(planning_split_tool=True).copy()
        self.assertEqual(slot.resource_id, self.resource_joseph)

    def test_unavailability_open_shift(self):
        gantt_unavailabilities = self.env["planning.slot"]._gantt_unavailability(
            "resource_id",
            self.resource_bert.ids,
            datetime(2024, 1, 1),
            datetime(2024, 1, 7),
            "month",
        )
        self.assertEqual(
            gantt_unavailabilities[False],
            [],
            "There should be no unavailability for open shifts.",
        )
        self.assertNotEqual(
            gantt_unavailabilities[self.resource_bert.id],
            [],
            "There should be unavailabilities for Bert.",
        )

    def test_batch_creation_from_calendar(self):
        template_valid, template_invalid = self.env["planning.slot.template"].create(
            [
                {
                    "start_time": 8,
                    "end_time": 12,
                    "duration_days": 1,
                },
                {
                    "start_time": 18,
                    "end_time": 20,
                    "duration_days": 1,
                },
            ]
        )
        self.employee_bert.resource_calendar_id = False
        self.employee_joseph.resource_calendar_id = self.company_calendar
        slot_joseph, slot_bert = self.env["planning.slot"].create_batch_from_calendar(
            [
                {
                    "start_datetime": "2025-04-04 08:00:00",
                    "end_datetime": "2025-04-04 12:00:00",
                    "resource_id": resource.id,
                    "template_id": template_valid.id,
                }
                for resource in (self.resource_joseph, self.resource_bert)
            ]
        )

        self.assertEqual(slot_joseph.resource_id, self.resource_joseph)
        self.assertEqual(
            slot_joseph.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-04 08:00:00",
        )
        self.assertEqual(
            slot_joseph.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-04 12:00:00",
        )
        self.assertEqual(slot_bert.resource_id, self.resource_bert)
        self.assertEqual(
            slot_bert.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-04 08:00:00",
        )
        self.assertEqual(
            slot_bert.end_datetime.strftime("%Y-%m-%d %H:%M:%S"), "2025-04-04 12:00:00"
        )

        slot_bert = self.env["planning.slot"].create_batch_from_calendar(
            [
                {
                    "start_datetime": "2025-04-04 18:00:00",
                    "end_datetime": "2025-04-04 20:00:00",
                    "resource_id": resource.id,
                    "template_id": template_invalid.id,
                }
                for resource in (self.resource_joseph, self.resource_bert)
            ]
        )
        self.assertEqual(slot_bert.resource_id, self.resource_bert)
        self.assertEqual(
            slot_bert.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-04 18:00:00",
        )
        self.assertEqual(
            slot_bert.end_datetime.strftime("%Y-%m-%d %H:%M:%S"), "2025-04-04 20:00:00"
        )

    def test_batch_creation_from_calendar_with_duration_days_template(self):
        shift_template = self.env["planning.slot.template"].create(
            {"start_time": 8, "end_time": 12, "duration_days": 5}
        )
        self.employee_bert.resource_calendar_id = False
        self.employee_joseph.resource_calendar_id = self.company_calendar

        slot_joseph_1, slot_bert_1, slot_joseph_2, slot_bert_2 = self.env[
            "planning.slot"
        ].create_batch_from_calendar(
            [
                {
                    "start_datetime": f"2025-04-{day[0]} 08:00:00",
                    "end_datetime": f"2025-04-{day[1]} 12:00:00",
                    "resource_id": resource.id,
                    "template_id": shift_template.id,
                }
                for day in [["07", "11"], ["08", "12"]]
                for resource in (self.resource_joseph, self.resource_bert)
            ]
        )
        self.assertEqual(slot_joseph_1.resource_id, self.resource_joseph)
        self.assertEqual(slot_joseph_2.resource_id, self.resource_joseph)
        self.assertEqual(slot_bert_1.resource_id, self.resource_bert)
        self.assertEqual(slot_bert_2.resource_id, self.resource_bert)
        self.assertEqual(
            slot_joseph_1.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-07 08:00:00",
        )
        self.assertEqual(
            slot_joseph_2.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-08 08:00:00",
        )
        self.assertEqual(
            slot_bert_1.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-07 08:00:00",
        )
        self.assertEqual(
            slot_bert_2.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-08 08:00:00",
        )
        self.assertEqual(
            slot_joseph_1.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-11 12:00:00",
        )
        self.assertEqual(
            slot_joseph_2.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-14 12:00:00",
        )
        self.assertEqual(
            slot_bert_1.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-11 12:00:00",
        )
        self.assertEqual(
            slot_bert_2.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "2025-04-12 12:00:00",
        )

    def test_copy_slots_when_time_off(self):
        employee_bert = self.env["hr.employee"].create(
            {
                "name": "Test",
                "work_email": "test@test.in",
                "tz": "UTC",
                "employee_type": "freelance",
                "create_date": "2015-01-01 00:00:00",
                "resource_calendar_id": self.company_calendar.id,
            }
        )

        PlanningSlot = self.env["planning.slot"]
        dt = datetime(2020, 1, 20, 0, 0)

        slot = PlanningSlot.create(
            {
                "resource_id": employee_bert.resource_id.id,
                "start_datetime": dt + relativedelta(hours=8),
                "end_datetime": dt + relativedelta(days=4, hours=17),
            }
        )

        self.env["resource.schedule.exception"].create(
            {
                "name": "I go to my father-in-law's",
                "calendar_id": employee_bert.resource_id.calendar_id.id,
                "date_from": dt + relativedelta(weeks=1, days=1),
                "date_to": dt + relativedelta(weeks=1, days=2, hours=17),
                "resource_id": employee_bert.resource_id.id,
            }
        )

        copied, _dummy = PlanningSlot.action_copy_previous_week(
            str(dt + relativedelta(weeks=1)),
            [
                ["start_datetime", "<=", dt + relativedelta(weeks=1)],
                ["end_datetime", ">=", dt],
                ["resource_id", "=", employee_bert.resource_id.id],
            ],
        )

        copied_slot = PlanningSlot.browse(copied)
        open_slot = copied_slot.filtered(lambda x: not x.resource_id)

        self.assertEqual(
            len(open_slot),
            4,
            "4 shift should be copied as open, as the employee is on off",
        )
        self.assertEqual(
            sum(open_slot.mapped("allocated_hours")),
            16,
            "16 hours should be allocated to open slot",
        )
        self.assertEqual(
            slot.allocated_hours,
            sum(copied_slot.mapped("allocated_hours")),
            "The allocated hours of slot and allocated hours of copied slots must be same",
        )

    def test_change_planning_template_start_or_end_time_to_invalid_value(self):
        with self.assertRaises(ValidationError):
            self.template.write({"end_time": 24})
            self.template.read()
        with self.assertRaises(ValidationError):
            self.template.write({"start_time": 24})
            self.template.read()
        self.assertEqual(self.template.end_time, 14)
        self.assertEqual(self.template.start_time, 11)

    def test_auto_plan_flexible_employee_no_rate_no_hours_day_overload(self):
        self.env.user.tz = "UTC"
        shift1, shift2 = self.env["planning.slot"].create(
            [
                {
                    "name": "Night Shift",
                    "start_datetime": datetime(2023, 7, 28, 8),
                    "end_datetime": datetime(2023, 7, 28, 16, 0),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 4,
                },
                {
                    "name": "Night Shift",
                    "start_datetime": datetime(2023, 7, 28, 8),
                    "end_datetime": datetime(2023, 7, 28, 16, 0),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 3,
                },
            ]
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(res["open_shift_assigned"], [shift1.id, shift2.id])
        self.assertEqual(shift1.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift2.resource_id.employee_id, self.flex_employee)

        self.assertEqual(
            shift1.allocated_hours, 4.0, "should be the same original value"
        )
        self.assertEqual(
            shift1.allocated_percentage, 50.0, "4 allocated hours / 8 working hours"
        )

        self.assertEqual(
            shift2.allocated_hours, 3.0, "should be the same original value"
        )
        self.assertEqual(
            shift2.allocated_percentage, 37.5, "4 allocated hours / 8 working hours"
        )

        shift3, shift4 = self.env["planning.slot"].create(
            [
                {
                    "name": "Night Shift",
                    "start_datetime": datetime(2023, 7, 28, 8),
                    "end_datetime": datetime(2023, 7, 28, 16),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 1,
                },
                {
                    "name": "Night Shift",
                    "start_datetime": datetime(2023, 7, 28, 8),
                    "end_datetime": datetime(2023, 7, 28, 16),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 2,
                },
            ]
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(
            res["open_shift_assigned"],
            [shift3.id],
            "shift 4 cannot be planned as it will create an overload",
        )
        self.assertEqual(
            shift3.resource_id.employee_id,
            self.flex_employee,
            "allocated_hours = 4 + 3 + 1 = 8 hours / allocated_percentage = 50 + 12.5 + 37.5 = 100%",
        )
        self.assertFalse(shift4.resource_id.employee_id)

        self.assertEqual(
            shift3.allocated_hours, 1.0, "should be the same original value"
        )
        self.assertEqual(
            shift3.allocated_percentage, 12.5, "1 allocated hour / 8 working hours"
        )

        shift5 = self.env["planning.slot"].create(
            {
                "name": "Night Shift",
                "start_datetime": datetime(2023, 7, 28, 6),
                "end_datetime": datetime(2023, 7, 28, 8),
                "role_id": self.flex_role.id,
                "allocated_hours": 2,
            }
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(
            res["open_shift_assigned"],
            [],
            "8 hours already consumed on day 28 from 8h to 16h",
        )

        self.employee_bert.write(
            {
                "resource_calendar_id": self.flex_40h_calendar.id,
                "default_planning_role_id": self.flex_role.id,
                "tz": "UTC",
            }
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(res["open_shift_assigned"], [shift4.id, shift5.id])
        self.assertEqual(shift4.resource_id.employee_id, self.employee_bert)
        self.assertEqual(shift5.resource_id.employee_id, self.employee_bert)

        self.assertEqual(
            shift4.allocated_hours, 2.0, "should be the same original value"
        )
        self.assertEqual(
            shift4.allocated_percentage, 25.0, "2 allocated hours / 8 working hours"
        )

        self.assertEqual(
            shift5.allocated_hours, 2.0, "should be the same original value"
        )
        self.assertEqual(
            shift5.allocated_percentage, 100.0, "2 allocated hour / 2 working hours"
        )

    def test_auto_plan_fully_flexible_employee_no_rate_no_hours_day_overload(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_calendar_id = False
        shift1, shift2, shift3, shift4 = self.env["planning.slot"].create(
            [
                {
                    "name": "Shift 1",
                    "start_datetime": datetime(2023, 7, 28, 2),
                    "end_datetime": datetime(2023, 7, 28, 23),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 10.5,
                },
                {
                    "name": "Shift 2",
                    "start_datetime": datetime(2023, 7, 28, 2),
                    "end_datetime": datetime(2023, 7, 28, 23),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 10.5,
                },
                {
                    "name": "Shift 3",
                    "start_datetime": datetime(2023, 7, 28, 0),
                    "end_datetime": datetime(2023, 7, 28, 2),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 2,
                },
                {
                    "name": "Shift 4",
                    "start_datetime": datetime(2023, 7, 28, 23),
                    "end_datetime": datetime(2023, 7, 29),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 1,
                },
            ]
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(
            res["open_shift_assigned"], [shift1.id, shift2.id, shift3.id, shift4.id]
        )
        self.assertEqual(shift1.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift2.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift3.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift4.resource_id.employee_id, self.flex_employee)

        self.assertEqual(
            shift1.allocated_hours, 10.5, "should be the same original value"
        )
        self.assertEqual(
            shift1.allocated_percentage,
            50.0,
            "10.5 allocated hours / 21 working hours from 2h to 23h",
        )

        self.assertEqual(
            shift2.allocated_hours, 10.5, "should be the same original value"
        )
        self.assertEqual(
            shift2.allocated_percentage,
            50.0,
            "10.5 allocated hours / 21 working hours from 2h to 23h",
        )

        self.assertEqual(
            shift3.allocated_hours, 2.0, "should be the same original value"
        )
        self.assertEqual(
            shift3.allocated_percentage,
            100.0,
            "2 allocated hours / 2 working hours from 0h to 2h",
        )

        self.assertEqual(
            shift4.allocated_hours, 1.0, "should be the same original value"
        )
        self.assertEqual(
            shift4.allocated_percentage,
            100.0,
            "1 allocated hour / 1 working hours from 23h to 0h (next day)",
        )

        self.env["planning.slot"].create(
            {
                "name": "Night Shift",
                "start_datetime": datetime(2023, 7, 28, 8),
                "end_datetime": datetime(2023, 7, 28, 16),
                "role_id": self.flex_role.id,
                "allocated_hours": 1,
            }
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2023-07-26 22:00:00",
                default_end_datetime="2023-08-01 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2023-08-01 22:00:00"],
                    ["end_datetime", ">", "2023-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(
            res["open_shift_assigned"],
            [],
            "employee already busy for the 24 hours on day 28",
        )

    def _create_flexible_reservation(self, start, stop, percentage=100):
        return self.env["resource.reservation"].create(
            {
                "name": "Other application booking",
                "resource_id": self.flex_employee.resource_id.id,
                "date_start": start,
                "date_end": stop,
                "allocated_percentage": percentage,
            }
        )

    def _create_flexible_open_shift(self, start, stop, hours):
        return self.env["planning.slot"].create(
            {
                "start_datetime": start,
                "end_datetime": stop,
                "allocated_hours": hours,
                "role_id": self.flex_role.id,
            }
        )

    def test_auto_plan_long_shift_keeps_its_allocation_when_window_is_clipped(self):
        self.env.user.tz = "UTC"
        assigned = self.env["planning.slot"].create(
            {
                "resource_id": self.flex_employee.resource_id.id,
                "start_datetime": datetime(2025, 7, 21, 8),
                "end_datetime": datetime(2025, 8, 1, 16),
                "allocated_percentage": 50,
            }
        )
        self.assertAlmostEqual(assigned.allocated_hours, 40)
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 10), 1
        )
        shift.auto_plan_id()
        self.assertEqual(
            shift.resource_id,
            self.flex_employee.resource_id,
            "Clipping a two-week shift must not double its 50% allocation",
        )

    def test_auto_plan_regular_shift_does_not_dilute_load_across_lunch(self):
        self.env.user.tz = "UTC"
        calendar = self.env["resource.calendar"].create(
            {"name": "Lunch break", "tz": "UTC"}
        )
        self.flex_employee.resource_calendar_id = calendar
        assigned = self.env["planning.slot"].create(
            {
                "resource_id": self.flex_employee.resource_id.id,
                "start_datetime": datetime(2025, 7, 28, 8),
                "end_datetime": datetime(2025, 7, 28, 17),
                "allocated_percentage": 100,
            }
        )
        self.assertAlmostEqual(assigned.allocated_hours, 8)
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 9), 0.1
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id,
            "An eight-hour shift with a lunch break still consumes 100% during work",
        )

    def test_auto_plan_capacity_covers_the_entire_reservation_span(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_calendar_id = self.env["resource.calendar"].create(
            {"name": "Lunch break capacity", "tz": "UTC"}
        )
        resource = self.flex_employee.resource_id
        for enforced in (False, True):
            for start, stop, ceiling, assigned in [
                (12, 13, 149, False),
                (12, 13, 150, True),
                (17, 18, 100, True),
                (7, 8, 100, True),
            ]:
                with (
                    self.subTest(enforced=enforced, start=start, ceiling=ceiling),
                    self.cr.savepoint(),
                ):
                    resource.write(
                        {
                            "enforce_booking_limit": enforced,
                            "booking_limit_percentage": ceiling,
                        }
                    )
                    booking = self._create_flexible_reservation(
                        datetime(2025, 7, 28, start),
                        datetime(2025, 7, 28, stop),
                        50,
                    )
                    shift = self._create_flexible_open_shift(
                        datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 17), 8
                    )
                    shift.auto_plan_id()
                    self.assertEqual(bool(shift.resource_id), assigned)
                    if assigned:
                        self.assertEqual(shift.resource_id, resource)
                        self.assertEqual(shift.allocated_percentage, 100)
                        self.assertEqual(shift.allocated_hours, 8)
                        self.assertLessEqual(
                            shift.reservation_ids.peak_booking_percentage, ceiling
                        )
                    shift.unlink()
                    booking.unlink()

    def test_auto_plan_batch_matches_sequential_capacity_and_budgets(self):
        self.env.user.tz = "UTC"
        resource = self.flex_employee.resource_id
        cases = [
            ("day", 100, [(28, 8, 12, 4), (28, 12, 17, 5)], [True, False]),
            ("week", 100, [(1, 8, 12, 4), (2, 8, 13, 5)], [True, False]),
            (
                "peak",
                150,
                [(28, 8, 10, 2), (28, 8, 10, 1), (28, 8, 10, 0.5)],
                [True, True, False],
            ),
        ]
        for enforced in (False, True):
            for name, ceiling, spans, expected in cases:
                for batch in (False, True):
                    with (
                        self.subTest(enforced=enforced, case=name, batch=batch),
                        self.cr.savepoint(),
                    ):
                        resource.write(
                            {
                                "enforce_booking_limit": enforced,
                                "booking_limit_percentage": ceiling,
                            }
                        )
                        bookings = self.env["resource.reservation"]
                        if name == "week":
                            for day in range(28, 32):
                                bookings |= self._create_flexible_reservation(
                                    datetime(2025, 7, day, 8),
                                    datetime(2025, 7, day, 16),
                                )
                        shifts = self.env["planning.slot"]
                        for day, start, stop, hours in spans:
                            month = 8 if name == "week" else 7
                            shifts |= self._create_flexible_open_shift(
                                datetime(2025, month, day, start),
                                datetime(2025, month, day, stop),
                                hours,
                            )
                        planner = shifts.with_context(
                            default_start_datetime=min(shifts.mapped("start_datetime")),
                            default_end_datetime=max(shifts.mapped("end_datetime")),
                        )
                        if batch:
                            result = planner.auto_plan_ids([("id", "in", shifts.ids)])
                            self.assertEqual(
                                result["open_shift_assigned"],
                                [
                                    shift.id
                                    for shift, assigned in zip(
                                        shifts, expected, strict=True
                                    )
                                    if assigned
                                ],
                            )
                        else:
                            for shift in shifts:
                                shift.auto_plan_id()
                        self.assertEqual(
                            [bool(shift.resource_id) for shift in shifts], expected
                        )
                        for shift, span, assigned in zip(
                            shifts, spans, expected, strict=True
                        ):
                            self.assertEqual(shift.allocated_hours, span[3])
                            if assigned:
                                self.assertEqual(shift.resource_id, resource)
                                self.assertEqual(len(shift.reservation_ids), 1)
                                self.assertLessEqual(
                                    shift.reservation_ids.peak_booking_percentage,
                                    ceiling,
                                )
                            else:
                                self.assertFalse(shift.reservation_ids)
                        reservations = shifts.reservation_ids
                        self.assertEqual(
                            planner.auto_plan_ids([("id", "in", shifts.ids)])[
                                "open_shift_assigned"
                            ],
                            [],
                        )
                        self.assertEqual(shifts.reservation_ids, reservations)
                        self.assertEqual(
                            [bool(shift.resource_id) for shift in shifts], expected
                        )
                        shifts.unlink()
                        bookings.unlink()

    def test_auto_plan_external_booking_day_uses_resource_timezone(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_id.tz = "Pacific/Auckland"
        self._create_flexible_reservation(
            datetime(2025, 7, 27, 22), datetime(2025, 7, 27, 23)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 0), datetime(2025, 7, 28, 1), 1
        )
        shift.auto_plan_id()
        self.assertEqual(shift.resource_id, self.flex_employee.resource_id)

    def test_auto_plan_flexible_day_uses_resource_timezone(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_id.tz = "Pacific/Auckland"
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 27, 22), datetime(2025, 7, 27, 23), 1
        )
        shift.auto_plan_id()
        self.assertEqual(
            shift.resource_id,
            self.flex_employee.resource_id,
            "Monday in Auckland is a valid working day even when the planner sees Sunday",
        )

    def test_auto_plan_flexible_week_uses_resource_timezone(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_id.tz = "Pacific/Auckland"
        for day in range(28, 32):
            self._create_flexible_reservation(
                datetime(2025, 7, day, 0), datetime(2025, 7, day, 8)
            )
        self._create_flexible_reservation(
            datetime(2025, 8, 1, 0), datetime(2025, 8, 1, 8)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 27, 22), datetime(2025, 7, 27, 23), 1
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id, "The resource's local week is already fully booked"
        )

    def test_auto_plan_external_booking_daily_budget(self):
        self.env.user.tz = "UTC"
        self._create_flexible_reservation(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 12)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 13), datetime(2025, 7, 28, 18), 5
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id, "Four booked hours leave only four hours that day"
        )
        shift.write({"end_datetime": datetime(2025, 7, 28, 17), "allocated_hours": 4})
        shift.auto_plan_id()
        self.assertEqual(shift.resource_id, self.flex_employee.resource_id)

    def test_auto_plan_external_booking_partial_daily_budget(self):
        self.env.user.tz = "UTC"
        self._create_flexible_reservation(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 16), 50
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 17), datetime(2025, 7, 28, 21), 4
        )
        shift.auto_plan_id()
        self.assertEqual(shift.resource_id, self.flex_employee.resource_id)

    def test_auto_plan_external_booking_permitted_overbooking(self):
        self.env.user.tz = "UTC"
        self._create_flexible_reservation(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 10), 50
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 10), 2
        )
        shift.auto_plan_id()
        self.assertFalse(shift.resource_id)
        self.flex_employee.resource_id.booking_limit_percentage = 150
        shift.auto_plan_id()
        self.assertEqual(shift.resource_id, self.flex_employee.resource_id)

    def test_auto_plan_enforced_ceiling_uses_final_assignment_percentage(self):
        self.env.user.tz = "UTC"
        self.env.company.resource_calendar_id.hours_per_day = 4
        resource = self.flex_employee.resource_id
        resource.enforce_booking_limit = True
        for existing, ceiling in [(25, 75), (50, 100), (100, 150)]:
            with self.subTest(existing=existing, ceiling=ceiling):
                resource.booking_limit_percentage = ceiling
                booking = self._create_flexible_reservation(
                    datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 10), existing
                )
                shift = self._create_flexible_open_shift(
                    datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 16), 4
                )
                self.assertEqual(shift.allocated_percentage, 100)
                shift.auto_plan_id()
                self.assertEqual(shift.resource_id, resource)
                self.assertEqual(shift.allocated_percentage, 50)
                self.assertEqual(shift.allocated_hours, 4)
                self.assertEqual(shift.reservation_ids.peak_booking_percentage, ceiling)
                shift.unlink()
                booking.unlink()

    def test_auto_plan_external_booking_fully_flexible(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_calendar_id = False
        self._create_flexible_reservation(
            datetime(2025, 7, 28, 8), datetime(2025, 7, 28, 16)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 7, 28, 17), datetime(2025, 7, 28, 21), 4
        )
        shift.auto_plan_id()
        self.assertEqual(shift.resource_id, self.flex_employee.resource_id)

    def test_auto_plan_external_booking_weekly_budget(self):
        self.env.user.tz = "UTC"
        for day in range(28, 32):
            self._create_flexible_reservation(
                datetime(2025, 7, day, 8), datetime(2025, 7, day, 16)
            )
        self._create_flexible_reservation(
            datetime(2025, 8, 1, 8), datetime(2025, 8, 1, 16)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 8, 2, 8), datetime(2025, 8, 2, 9), 1
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id, "The forty-hour week is already fully booked"
        )

    def test_auto_plan_sunday_uses_resource_week(self):
        self.env.user.tz = "UTC"
        self.env.user.lang = "en_US"
        for day in range(28, 32):
            self._create_flexible_reservation(
                datetime(2025, 7, day, 8), datetime(2025, 7, day, 16)
            )
        self._create_flexible_reservation(
            datetime(2025, 8, 1, 8), datetime(2025, 8, 1, 16)
        )
        shift = self._create_flexible_open_shift(
            datetime(2025, 8, 3, 8), datetime(2025, 8, 3, 9), 1
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id,
            "Sunday belongs to the same resource budget week as Monday",
        )

    def test_auto_plan_multiday_shift_weekly_remainder(self):
        self.env.user.tz = "UTC"
        for day, hours in [(28, 8), (29, 8), (30, 8), (31, 2)]:
            self.env["planning.slot"].create(
                {
                    "resource_id": self.flex_employee.resource_id.id,
                    "start_datetime": datetime(2025, 7, day, 8),
                    "end_datetime": datetime(2025, 7, day, 8 + hours),
                    "allocated_hours": hours,
                }
            )
        shift = self._create_flexible_open_shift(
            datetime(2025, 8, 1, 8), datetime(2025, 8, 2, 16), 16
        )
        shift.auto_plan_id()
        self.assertFalse(
            shift.resource_id,
            "Two eight-hour days exceed the fourteen-hour weekly remainder",
        )

    def test_auto_plan_flexible_employee_no_week_overload(self):
        self.env.user.tz = "UTC"

        shift1, shift2, shift3, shift4, shift5 = self.env["planning.slot"].create(
            [
                {
                    "name": "Shift 1",
                    "start_datetime": datetime(2025, 7, 28, 8),
                    "end_datetime": datetime(2025, 7, 30, 16),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 12,
                },
                {
                    "name": "Shift 2",
                    "start_datetime": datetime(2025, 7, 28, 8),
                    "end_datetime": datetime(2025, 7, 30, 16, 0),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 12,
                },
                {
                    "name": "Shift 3",
                    "start_datetime": datetime(2025, 7, 31, 8),
                    "end_datetime": datetime(2025, 7, 31, 16),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 8,
                },
                {
                    "name": "Shift 4",
                    "start_datetime": datetime(2025, 8, 1, 8),
                    "end_datetime": datetime(2025, 8, 1, 16),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 8,
                },
                {
                    "name": "Shift 5",
                    "start_datetime": datetime(2025, 8, 2, 8),
                    "end_datetime": datetime(2025, 8, 2, 16, 0),
                    "role_id": self.flex_role.id,
                    "allocated_hours": 8,
                },
            ]
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2025-07-26 22:00:00",
                default_end_datetime="2025-08-04 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2025-08-04 22:00:00"],
                    ["end_datetime", ">", "2025-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(
            res["open_shift_assigned"],
            [shift1.id, shift2.id, shift3.id, shift4.id],
            "shift 5 cannot be planned as it will create an overload on the week",
        )
        self.assertEqual(shift1.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift2.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift3.resource_id.employee_id, self.flex_employee)
        self.assertEqual(shift4.resource_id.employee_id, self.flex_employee)
        self.assertFalse(shift5.resource_id.employee_id)

        self.assertEqual(
            shift1.allocated_hours, 12.0, "should be the same original value"
        )
        self.assertEqual(
            shift1.allocated_percentage,
            50.0,
            "12 allocated hours / 24 working hours from 8h day 28 to 16h day 30",
        )

        self.assertEqual(
            shift2.allocated_hours, 12.0, "should be the same original value"
        )
        self.assertEqual(
            shift2.allocated_percentage,
            50.0,
            "12 allocated hours / 24 working hours from 8h day 28 to 16h day 30",
        )

        self.assertEqual(
            shift3.allocated_hours, 8.0, "should be the same original value"
        )
        self.assertEqual(
            shift3.allocated_percentage,
            100.0,
            "8 allocated hours / 8 working hours from 8h to 16h day 31",
        )

        self.assertEqual(
            shift4.allocated_hours, 8.0, "should be the same original value"
        )
        self.assertEqual(
            shift4.allocated_percentage,
            100.0,
            "8 allocated hours / 8 working hours from 8h to 16h day 01",
        )

    def test_auto_plan_fully_flexible_employee_no_hours_limit_per_week(self):
        self.env.user.tz = "UTC"
        self.flex_employee.resource_calendar_id = False

        shift = self.env["planning.slot"].create(
            {
                "name": "Shift 1",
                "start_datetime": datetime(2025, 7, 27),
                "end_datetime": datetime(2025, 8, 2),
                "role_id": self.flex_role.id,
                "allocated_hours": 120.0,
            }
        )

        res = (
            self.env["planning.slot"]
            .with_context(
                default_start_datetime="2025-07-26 22:00:00",
                default_end_datetime="2025-08-04 22:00:00",
            )
            .auto_plan_ids(
                [
                    "&",
                    ["start_datetime", "<", "2025-08-04 22:00:00"],
                    ["end_datetime", ">", "2025-07-26 22:00:00"],
                ]
            )
        )

        self.assertEqual(res["open_shift_assigned"], [shift.id])
        self.assertEqual(shift.resource_id.employee_id, self.flex_employee)

    def test_print_planning(self):
        flexEmployee, standardEmployee = self.env["hr.employee"].create(
            [
                {
                    "name": "Flex Employee",
                    "tz": "UTC",
                },
                {
                    "name": "Standard Employee",
                    "tz": "UTC",
                },
            ]
        )

        flexEmployee.resource_id.calendar_id = self.flex_40h_calendar
        standardEmployee.resource_id.calendar_id = self.company_calendar
        slots_count = self.env["planning.slot"].search_count([])

        self.env.user.tz = "UTC"
        slot1, slot2, slot3 = (
            self.env["planning.slot"]
            .with_context(tz="UTC")
            .create(
                [
                    {
                        "resource_id": flexEmployee.resource_id.id,
                        "start_datetime": datetime(2025, 5, 16, 8, 0, 0),
                        "end_datetime": datetime(2025, 5, 20, 17, 0, 0),
                    },
                    {
                        "resource_id": standardEmployee.resource_id.id,
                        "start_datetime": datetime(2025, 5, 21, 8, 0, 0),
                        "end_datetime": datetime(2025, 5, 26, 17, 0, 0),
                    },
                    {
                        "start_datetime": datetime(2025, 5, 16, 8, 0, 0),
                        "end_datetime": datetime(2025, 5, 19, 17, 0, 0),
                    },
                ]
            )
        )

        slots = slot1 | slot2 | slot3
        current_slots_count = self.env["planning.slot"].search_count([])
        self.assertEqual(
            current_slots_count, len(slots) + slots_count, "3 slots should be created"
        )

        field_involved_in_fake_pill_creating_and_updating = (
            slots._print_planning_get_fields_to_copy()
        )

        def get_slots_values(slots):
            values = {}
            for slot in slots:
                values[slot.id] = {
                    field: slot[field]
                    for field in field_involved_in_fake_pill_creating_and_updating
                }

            return values

        original_values = get_slots_values(slots)

        action = (
            self.env["planning.slot"]
            .with_context(discard_logo_check=True)
            .action_print_plannings(
                date_start="2025-05-18 00:00:00",
                date_end="2025-05-24 23:59:59",
                group_bys=["resource_id"],
                domain=[
                    ["start_datetime", "<", "2025-05-25 00:00:00"],
                    ["end_datetime", ">", "2025-05-18 00:00:00"],
                ],
            )
        )

        self.assertEqual(
            current_slots_count,
            self.env["planning.slot"].search_count([]),
            "no additional slots should be created",
        )
        all_slots = self.env["planning.slot"].search(
            [
                ["start_datetime", "<", "2025-05-25 00:00:00"],
                ["end_datetime", ">", "2025-05-18 00:00:00"],
            ]
        )

        slots_after_printing = all_slots & slots
        self.assertDictEqual(original_values, get_slots_values(slots_after_printing))

        self.assertEqual(
            len(action["data"]["group_by_slots_per_day_per_week"]), 1, "one week"
        )
        self.assertEqual(len(action["data"]["group_by_slots_per_day_per_week"][0]), 3)

        self.assertEqual(
            action["data"]["group_by_slots_per_day_per_week"][0][0],
            (
                False,
                {
                    "05/18/2025": [
                        {
                            "title": "00:00 – 23:59",
                            "style": "background-color: #80c3c2;",
                        }
                    ],
                    "05/19/2025": [
                        {
                            "title": "00:00 – 17:00",
                            "style": "background-color: #80c3c2;",
                        }
                    ],
                },
            ),
        )


        self.assertEqual(
            action["data"]["group_by_slots_per_day_per_week"][0][1][0],
            flexEmployee.resource_id.id,
        )
        self.assertDictEqual(
            action["data"]["group_by_slots_per_day_per_week"][0][1][1],
            {
                "05/18/2025": [
                    {"title": "00:00 – 23:59", "style": "background-color: #80c3c2;"}
                ],
                "05/19/2025": [
                    {"title": "00:00 – 23:59", "style": "background-color: #80c3c2;"}
                ],
                "05/20/2025": [
                    {"title": "00:00 – 17:00", "style": "background-color: #80c3c2;"}
                ],
            },
        )

        self.assertEqual(
            action["data"]["group_by_slots_per_day_per_week"][0][2][0],
            standardEmployee.resource_id.id,
        )
        self.assertDictEqual(
            action["data"]["group_by_slots_per_day_per_week"][0][2][1],
            {
                "05/21/2025": [
                    {"title": "08:00 – 17:00", "style": "background-color: #80c3c2;"}
                ],
                "05/22/2025": [
                    {"title": "06:00 – 15:00", "style": "background-color: #80c3c2;"}
                ],
                "05/23/2025": [
                    {"title": "08:00 – 17:00", "style": "background-color: #80c3c2;"}
                ],
            },
        )

        self.assertEqual(
            action["data"]["weeks"][0],
            (
                0,
                [
                    "05/18/2025",
                    "05/19/2025",
                    "05/20/2025",
                    "05/21/2025",
                    "05/22/2025",
                    "05/23/2025",
                    "05/24/2025",
                ],
                "Week from 05/18/2025 to 05/24/2025",
            ),
        )

    def test_gantt_progress_bar_split_when_flexible(self):
        self.employee_bert.resource_calendar_id = self.flex_40h_calendar.id

        dt = datetime(2025, 8, 22, 0, 0)

        self.slot.write(
            {
                "resource_id": self.employee_bert.resource_id.id,
                "start_datetime": dt + relativedelta(hours=8),
                "end_datetime": dt + relativedelta(days=4, hours=17),
            }
        )

        planning_hours_info_1st_week = self.env["planning.slot"]._gantt_progress_bar(
            "resource_id",
            self.employee_bert.resource_id.ids,
            datetime(2025, 8, 16),
            datetime(2025, 8, 23, 23, 59),
        )

        self.assertEqual(self.slot.allocated_hours, 40.0)
        self.assertEqual(
            planning_hours_info_1st_week[self.employee_bert.resource_id.id]["value"], 16
        )

        planning_hours_info_2nd_week = self.env["planning.slot"]._gantt_progress_bar(
            "resource_id",
            self.employee_bert.resource_id.ids,
            datetime(2025, 8, 24),
            datetime(2025, 8, 30, 23, 59),
        )

        self.assertEqual(
            planning_hours_info_2nd_week[self.employee_bert.resource_id.id]["value"], 24
        )

    def test_compute_slots_data(self):
        employee_a, employee_b = self.env["hr.employee"].create(
            [
                {"name": "Employee A"},
                {"name": "Employee B"},
            ]
        )

        role_dev, role_other = self.env["resource.role"].create(
            [
                {"name": "Dev"},
                {"name": "Tester"},
            ]
        )

        slot_in_range = self.env["planning.slot"].create(
            [
                {
                    "start_datetime": datetime(2023, 11, 20, 9, 0),
                    "end_datetime": datetime(2023, 11, 20, 16, 0),
                    "employee_id": employee_a.id,
                    "resource_id": employee_a.resource_id.id,
                    "resource_type": "human",
                    "role_id": role_other.id,
                },
                {
                    "start_datetime": datetime(2023, 11, 19, 9, 0),
                    "end_datetime": datetime(2023, 11, 19, 16, 0),
                    "employee_id": employee_b.id,
                    "resource_id": employee_b.resource_id.id,
                    "resource_type": "human",
                    "role_id": role_dev.id,
                },
            ]
        )
        slot_in_range = slot_in_range[0]

        wizard = self.env["wizard.planning.slot.publish"].create(
            {
                "start_datetime": datetime(2023, 11, 20, 8, 0),
                "end_datetime": datetime(2023, 11, 20, 17, 0),
            }
        )
        wizard._compute_slots_data()

        self.assertIn(
            slot_in_range,
            wizard.slot_ids,
            "Wizard should include slots inside the range.",
        )

        self.assertEqual(
            wizard.resource_ids,
            employee_a.resource_id,
        )

        wizard_ctx = wizard.with_context(active_domain=[("role_id", "=", role_dev.id)])
        wizard_ctx._compute_slots_data()
        self.assertFalse(
            wizard_ctx.slot_ids,
        )

    @freeze_time("2019-5-28 08:00:00")
    def test_user_assign_shift_multicompany(self):
        company = self.env["res.company"].create({"name": "Test company"})
        self.env.user.company_ids += company
        test_slot = self.env["planning.slot"].create(
            {
                "start_datetime": datetime(2019, 5, 28, 8, 0, 0),
                "end_datetime": datetime(2019, 5, 28, 17, 0, 0),
                "state": "2_published",
                "company_id": company.id,
            }
        )
        with self.assertRaises(UserError):
            test_slot.with_company(company).action_self_assign()
        employee = self.env["hr.employee"].create(
            {
                "name": "odoobot",
                "work_email": "odoobot@example.com",
                "tz": "UTC",
                "employee_type": "freelance",
                "create_date": "2015-01-01 00:00:00",
                "user_id": self.env.user.id,
                "company_id": company.id,
            }
        )
        test_slot.with_company(company).action_self_assign()
        self.assertEqual(test_slot.employee_id, employee)

    def test_avatar_card_archived_employee_info(self):
        employee = self.env["hr.employee"].create(
            {
                "active": False,
                "name": "Test Emp",
            }
        )
        data = employee.resource_id.get_avatar_card_data(["name"])[0]
        self.assertEqual(data.get("name"), "Test Emp")

    def test_multi_shift_creation_excludes_non_working_days(self):
        self.employee_bert.resource_calendar_id = self.flex_40h_calendar
        slots = (
            self.env["planning.slot"]
            .with_context(multi_create=True)
            .create(
                [
                    {
                        "start_datetime": datetime(2025, 10, day, 9, 0, 0),
                        "end_datetime": datetime(2025, 10, day, 17, 0, 0),
                        "resource_id": resource.id,
                        "template_id": self.template.id,
                    }
                    for day in range(5, 12)
                    for resource in [
                        self.resource_janice,
                        self.resource_bert,
                        self.resource_joseph,
                    ]
                ]
            )
        )

        slots_janice = slots.filtered(
            lambda slot: slot.resource_id == self.resource_janice
        )
        slots_bert = slots.filtered(lambda slot: slot.resource_id == self.resource_bert)

        self.assertEqual(
            len(slots_janice),
            5,
            "Standard schedule: shifts should be created only on working days.",
        )
        self.assertEqual(
            [slot.start_datetime.day for slot in slots_janice],
            [6, 7, 8, 9, 10],
            "Excluded 5 and 11 (Sat/Sun)",
        )
        self.assertEqual(
            len(slots_bert),
            5,
            "Flexible schedule: shifts should be created only on working days.",
        )
        self.assertEqual(
            [slot.start_datetime.day for slot in slots_bert],
            [6, 7, 8, 9, 10],
            "a week's hours fall from its first day, Monday: Sunday 5 and Saturday "
            "11 hold none of them",
        )

    def test_planning_send_action_check_emails(self):
        start_datetime = datetime(2024, 7, 1, 8, 0)
        end_datetime = datetime(2024, 7, 1, 17, 0)
        beth_shift, joseph_shift = self.env["planning.slot"].create(
            [
                {
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "resource_id": self.resource_bert.id,
                },
                {
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "resource_id": self.resource_joseph.id,
                },
            ]
        )
        self.assertEqual(
            beth_shift.state, "1_draft", "The shift should be in draft state by default"
        )
        self.assertEqual(
            joseph_shift.state,
            "1_draft",
            "The shift should be in draft state by default",
        )

        self.employee_bert.work_email = ""

        planning_send_wizard = self.env["wizard.planning.slot.publish"].create(
            {
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "slot_ids": (beth_shift + joseph_shift).ids,
            }
        )
        self.assertTrue(self.env["hr.employee"].has_access("write"))
        action = planning_send_wizard.action_check_emails()
        self.assertEqual(action["name"], "No Email Address for Some People")
        self.assertEqual(
            action["type"],
            "ir.actions.act_window",
            "The action should open a form view to complete missing work email",
        )

        self.assertFalse(
            self.env["hr.employee"]
            .with_user(self.planning_manager_user)
            .has_access("write")
        )
        action = planning_send_wizard.with_user(
            self.planning_manager_user
        ).action_check_emails()
        self.assertEqual(
            action["type"],
            "ir.actions.client",
            "The action should return a notification",
        )
        self.assertEqual(
            action["tag"],
            "display_notification",
            "The action should return a notification",
        )
        self.assertDictEqual(
            action["params"],
            {
                "type": "info",
                "message": "Shifts published — people without an email address were skipped",
                "next": {"type": "ir.actions.act_window_close"},
            },
        )
        self.assertEqual(
            beth_shift.state,
            "1_draft",
            "The shift should not be in published state after sending the planning since the employee set has no work_email and so no way to receive the planning",
        )
        self.assertEqual(
            joseph_shift.state,
            "2_published",
            "The shift should be in published state after sending the planning",
        )

    def test_repeat_until_before_start_datetime_raises(self):
        with self.assertRaises(UserError):
            self.env["planning.slot"].create(
                {
                    "start_datetime": datetime(2019, 6, 27, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 27, 18, 0, 0),
                    "repeat": True,
                    "repeat_type": "until",
                    "repeat_until": date(2019, 6, 20),
                }
            )

    def test_end_datetime_before_start_datetime_raises(self):
        with (
            self.assertRaises(IntegrityError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self.env["planning.slot"].create(
                {
                    "start_datetime": datetime(2019, 6, 27, 18, 0, 0),
                    "end_datetime": datetime(2019, 6, 27, 8, 0, 0),
                }
            )
            self.env.flush_all()

    def test_group_expand_resource_id_expands_on_department(self):
        department = self.env["hr.department"].create({"name": "Test Department"})
        (self.employee_joseph + self.employee_bert).department_id = department
        self.env["planning.slot"].create(
            {
                "resource_id": self.employee_joseph.resource_id.id,
                "start_datetime": datetime(2019, 6, 27, 8, 0),
                "end_datetime": datetime(2019, 6, 27, 17, 0),
            }
        )
        domain = [
            "&",
            "|",
            ["department_id", "ilike", "Test Department"],
            ["resource_id", "=", False],
            "&",
            ["start_datetime", "<", datetime(2019, 7, 4, 18, 30)],
            ["end_datetime", ">", datetime(2019, 6, 20, 18, 30)],
        ]

        expanded = (
            self.env["planning.slot"]
            .with_context(planning_expand_resource=True)
            ._group_expand_resource_id(
                (self.employee_joseph + self.employee_bert).resource_id, domain
            )
        )

        self.assertIn(
            self.employee_joseph.resource_id,
            expanded,
            "The resource holding a shift stays listed.",
        )
        self.assertIn(
            self.employee_bert.resource_id,
            expanded,
            "A member of the filtered department must be listed even with no shift.",
        )

    def test_open_shifts_action_expands_roles_without_shifts(self):
        role = self.env["resource.role"].create({"name": "Bartender"})
        action = self.env.ref("planning.planning_action_view_shifts")
        context = literal_eval(action.context)
        domain = [
            ["role_id", "ilike", "Bartender"],
            ["start_datetime", "<", datetime(2019, 7, 4, 18, 30)],
            ["end_datetime", ">", datetime(2019, 6, 20, 18, 30)],
        ]

        expanded = (
            self.env["planning.slot"]
            .with_context(**context)
            ._read_group_role_id(self.env["resource.role"], domain)
        )

        self.assertIn(
            role,
            expanded,
            "Filtering Open Shifts by a role must show that role's row even "
            "when it has no shift yet.",
        )
