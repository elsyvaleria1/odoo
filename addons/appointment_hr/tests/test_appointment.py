from datetime import UTC, date, datetime, timedelta

from freezegun import freeze_time

from odoo.tests import tagged, users

from odoo.addons.appointment_hr.tests.common import AppointmentHrCommon


@tagged("appointment_slots")
class AppointmentHrTest(AppointmentHrCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apt_type_bxls_2days.write(
            {
                "work_hours_activated": True,
            }
        )

    @users("apt_manager")
    def test_appointment_duplicate(self):
        appointments = self.env["appointment.type"].create(
            [
                {
                    "appointment_tz": "Europe/Brussels",
                    "appointment_duration": 1,
                    "is_auto_assign": True,
                    "category": "recurring",
                    "name": f"Appointment Test {apt_no}",
                    "min_cancellation_hours": 1,
                    "min_schedule_hours": 1,
                    "max_schedule_days": 30,
                    "staff_user_ids": [(4, self.env.uid)],
                }
                for apt_no in range(10)
            ]
        )
        appointments_copy = appointments.copy()
        self.assertEqual(len(appointments_copy), len(appointments))
        for appointment, appointment_copy in zip(
            appointments, appointments_copy, strict=False
        ):
            self.assertEqual(appointment_copy.name, f"{appointment.name} (copy)")

    @users("apt_manager")
    def test_generate_slots_recurring(self):
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        exp_months = [
            {
                "name_formated": "February 2022",
                "month_date": datetime(2022, 2, 1),
                "weeks_count": 5,
            }
        ]
        slots_data = {
            "enddate": self.global_slots_enddate,
            "startdate": self.reference_now_monthweekstart,
            "slots_startdate": self.reference_monday.date(),
            "slots_weekdays_nowork": range(
                2, 7
            ),
        }

        self.assertNotEqual(
            self.staff_employee_bxls.resource_calendar_id.schedule_type, "flexible"
        )
        with freeze_time(self.reference_now):
            slots = apt_type._get_appointment_slots("Europe/Brussels")
        slots_data.update({"slots_start_hours": [8, 9, 10, 11, 13]})
        self.assertSlots(slots, exp_months, slots_data)

        self.staff_employee_bxls.resource_calendar_id.write(
            {"schedule_type": "flexible"}
        )
        with freeze_time(self.reference_now):
            slots = apt_type._get_appointment_slots("Europe/Brussels")
        slots_data.update({"slots_start_hours": [8, 9, 10, 11, 12, 13]})
        self.assertSlots(slots, exp_months, slots_data)

    @users("apt_manager")
    def test_generate_slots_recurring_midnight(self):
        late_night_cal = (
            self.env["resource.calendar"]
            .sudo()
            .create(
                {
                    "attendance_ids": [
                        (
                            0,
                            0,
                            {
                                "dayofweek": f"{day - 1}",
                                "hour_from": hour,
                                "hour_to": hour + 4,
                                "name": f"Day {day} H {hour} {hour + 4}",
                            },
                        )
                        for hour in [0, 20]
                        for day in [1, 2, 3, 4]
                    ],
                    "company_id": self.company_admin.id,
                    "name": "00:00-04:00 and 20:00-00:00 on Mondays through Thursday",
                    "tz": "UTC",
                }
            )
        )

        current_employee_sudo = self.env.user.employee_id.sudo()
        current_employee_sudo.resource_calendar_id = late_night_cal
        current_employee_sudo.tz = "UTC"

        apt_type = self.env["appointment.type"].create(
            {
                "appointment_duration": 1,
                "appointment_tz": "UTC",
                "category": "recurring",
                "name": "Midnight Test",
                "max_schedule_days": 4,
                "min_cancellation_hours": 1,
                "min_schedule_hours": 0,
                "slot_ids": [
                    (
                        0,
                        False,
                        {
                            "weekday": "1",
                            "start_hour": hour,
                            "end_hour": (hour + 1) % 24,
                        },
                    )
                    for hour in [0, 1, 2, 21, 22, 23]
                ]
                + [
                    (
                        0,
                        False,
                        {
                            "weekday": "2",
                            "start_hour": hour,
                            "end_hour": hour + 1,
                        },
                    )
                    for hour in [0, 1, 2]
                ]
                + [
                    (
                        0,
                        False,
                        {
                            "weekday": "2",
                            "start_hour": 20,
                            "end_hour": 00,
                        },
                    )
                ]
                + [
                    (
                        0,
                        False,
                        {
                            "weekday": "3",
                            "start_hour": hour,
                            "end_hour": (hour + 5) % 24,
                        },
                    )
                    for hour in [0, 19]
                ],
                "staff_user_ids": self.env.user.ids,
                "work_hours_activated": True,
            }
        )

        with freeze_time(self.reference_monday.replace(hour=1, minute=36)):
            slots = apt_type._get_appointment_slots("UTC")

        self.assertSlots(
            slots,
            [
                {
                    "name_formated": "February 2022",
                    "month_date": datetime(2022, 2, 1),
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
                "slots_day_specific": {
                    self.reference_monday.date(): [
                        {
                            "start": 2,
                            "end": 3,
                        },
                        {"start": 21, "end": 22},
                        {"start": 22, "end": 23},
                        {"start": 23, "end": 00},
                    ],
                    (self.reference_monday + timedelta(days=1)).date(): [
                        {"start": 0, "end": 1},
                        {"start": 1, "end": 2},
                        {"start": 2, "end": 3},
                        {"start": 20, "end": 21},
                        {"start": 21, "end": 22},
                        {"start": 22, "end": 23},
                        {"start": 23, "end": 00},
                    ],
                    (self.reference_monday + timedelta(days=2)).date(): [
                        {"start": 0, "end": 1},
                        {"start": 1, "end": 2},
                        {"start": 2, "end": 3},
                        {
                            "start": 3,
                            "end": 4,
                        },
                        {"start": 20, "end": 21},
                        {"start": 21, "end": 22},
                        {"start": 22, "end": 23},
                        {"start": 23, "end": 00},
                    ],
                },
                "slots_startdate": self.reference_monday.date(),
            },
        )

    @users("apt_manager")
    def test_generate_slots_recurring_UTC(self):
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        with freeze_time(self.reference_now):
            slots = apt_type._get_appointment_slots("UTC")

        self.assertSlots(
            slots,
            [
                {
                    "name_formated": "February 2022",
                    "month_date": datetime(2022, 2, 1),
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
                "slots_start_hours": [
                    7,
                    8,
                    9,
                    10,
                    12,
                ],
                "slots_startdate": self.reference_monday.date(),
                "slots_weekdays_nowork": range(
                    2, 7
                ),
            },
        )

    @users("apt_manager")
    def test_generate_slots_recurring_wleaves(self):
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        _leaves = self._create_leaves(
            self.staff_user_bxls,
            [
                (
                    self.reference_monday + timedelta(days=1),
                    self.reference_monday + timedelta(days=1, hours=2),
                ),
                (
                    self.reference_monday + timedelta(days=7),
                    self.reference_monday + timedelta(days=7, hours=1),
                ),
            ],
        )
        _leaves += self._create_leaves(
            self.env["res.users"],
            [
                (
                    self.reference_monday
                    + timedelta(days=8),
                    self.reference_monday + timedelta(days=8, hours=12),
                )
            ],
            calendar=self.staff_user_bxls.resource_calendar_id,
        )

        with freeze_time(self.reference_now):
            slots = apt_type._get_appointment_slots("Europe/Brussels")

        self.assertSlots(
            slots,
            [
                {
                    "name_formated": "February 2022",
                    "month_date": datetime(2022, 2, 1),
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
                "slots_day_specific": {
                    (self.reference_monday + timedelta(days=1)).date(): [
                        {"end": 11, "start": 10},
                        {"end": 12, "start": 11},
                        {"end": 14, "start": 13},
                    ],
                    (self.reference_monday + timedelta(days=7)).date(): [
                        {"end": 10, "start": 9},
                        {"end": 11, "start": 10},
                        {"end": 12, "start": 11},
                        {"end": 14, "start": 13},
                    ],
                    (
                        self.reference_monday + timedelta(days=8)
                    ).date(): [],
                },
                "slots_start_hours": [
                    8,
                    9,
                    10,
                    11,
                    13,
                ],
                "slots_startdate": self.reference_monday.date(),
                "slots_weekdays_nowork": range(
                    2, 7
                ),
            },
        )

    @users("apt_manager")
    def test_generate_slots_recurring_wmeetings(self):
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        _meetings = self._create_meetings(
            self.staff_user_bxls,
            [
                (
                    self.reference_monday + timedelta(days=1),
                    self.reference_monday + timedelta(days=1, hours=3),
                    False,
                ),
                (
                    self.reference_monday
                    + timedelta(days=7),
                    self.reference_monday + timedelta(days=7, hours=1),
                    True,
                ),
                (
                    self.reference_monday
                    + timedelta(days=8, hours=2),
                    self.reference_monday + timedelta(days=8, hours=3),
                    False,
                ),
                (
                    self.reference_monday
                    + timedelta(
                        days=8, hours=3
                    ),
                    self.reference_monday + timedelta(days=8, hours=4),
                    False,
                ),
                (
                    self.reference_monday
                    + timedelta(days=8, hours=5),
                    self.reference_monday + timedelta(days=8, hours=7),
                    False,
                ),
            ],
        )
        attendee = _meetings[-2].attendee_ids.filtered(
            lambda att: att.partner_id == self.staff_user_bxls.partner_id
        )
        attendee.do_decline()

        with freeze_time(self.reference_now):
            slots = apt_type._get_appointment_slots("Europe/Brussels")

        self.assertSlots(
            slots,
            [
                {
                    "name_formated": "February 2022",
                    "month_date": datetime(2022, 2, 1),
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
                "slots_day_specific": {
                    (self.reference_monday + timedelta(days=1)).date(): [
                        {"end": 12, "start": 11},
                        {"end": 14, "start": 13},
                    ],
                    (
                        self.reference_monday + timedelta(days=7)
                    ).date(): [],
                    (self.reference_monday + timedelta(days=8)).date(): [
                        {"end": 9, "start": 8},
                        {"end": 10, "start": 9},
                        {"end": 12, "start": 11},
                    ],
                },
                "slots_start_hours": [
                    8,
                    9,
                    10,
                    11,
                    13,
                ],
                "slots_startdate": self.reference_monday.date(),
                "slots_weekdays_nowork": range(
                    2, 7
                ),
            },
        )

    def test_work_hours_follow_the_employee_version_in_force_on_each_day(self):
        weekdays, monday_only = self.env["resource.calendar"].create(
            [
                {"name": "Weekdays", "tz": "UTC"},
                {
                    "name": "Monday only",
                    "tz": "UTC",
                    "attendance_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Monday",
                                "dayofweek": "0",
                                "hour_from": 8,
                                "hour_to": 17,
                            },
                        )
                    ],
                },
            ]
        )
        user = self.env["res.users"].create(
            {"name": "Versioned staff", "login": "versioned_staff", "tz": "UTC"}
        )
        employee = self.env["hr.employee"].create(
            {
                "name": "Versioned staff",
                "user_id": user.id,
                "resource_calendar_id": weekdays.id,
                "date_version": date(2030, 1, 1),
                "contract_date_start": date(2030, 1, 1),
            }
        )
        employee.create_version(
            {"date_version": date(2030, 6, 3), "resource_calendar_id": monday_only.id}
        )
        start = datetime(2030, 5, 27, tzinfo=UTC)
        stop = datetime(2030, 6, 8, tzinfo=UTC)

        schedules = (
            self.apt_type_bxls_2days._slot_availability_prepare_users_values_workhours(
                user, start, stop
            )["work_schedules"][user.partner_id]
        )

        self.assertEqual(
            sorted({interval_start.date() for interval_start, _stop in schedules}),
            [date(2030, 5, 27 + day) for day in range(5)] + [date(2030, 6, 3)],
        )
