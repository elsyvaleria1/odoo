import random
import time
from datetime import date, timedelta
from logging import getLogger

from freezegun import freeze_time

from odoo.tests import tagged, users
from odoo.tests.common import warmup

from odoo.addons.appointment_hr.tests.common import AppointmentHrCommon
from odoo.addons.calendar.tests.booking.test_performance import (
    AppointmentPerformanceCase,
    AppointmentUIPerformanceCase,
)

_logger = getLogger(__name__)


class AppointmenHrPerformanceCase(AppointmentHrCommon, AppointmentPerformanceCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_calendar = cls.env["resource.calendar"].create(
            {
                "company_id": cls.company_admin.id,
                "name": "Test Calendar",
                "tz": "Europe/Brussels",
            }
        )

        cls.staff_users = (
            cls.env["res.users"]
            .with_context(cls._test_context)
            .create(
                [
                    {
                        "company_id": cls.company_admin.id,
                        "company_ids": [(4, cls.company_admin.id)],
                        "email": "brussels.%s@test.example.com" % idx,
                        "group_ids": [(4, cls.env.ref("base.group_user").id)],
                        "name": "Employee Brussels %s" % idx,
                        "login": "staff_users_bxl_%s" % idx,
                        "notification_type": "email",
                        "tz": "Europe/Brussels",
                    }
                    for idx in range(20)
                ]
            )
        )
        cls.resources = cls.env["resource.resource"].create(
            [{"name": "Resource %s" % idx, "type": "material"} for idx in range(20)]
        )

        cls.staff_users_resources = cls.env["resource.resource"].create(
            [
                {
                    "calendar_id": cls.test_calendar.id,
                    "company_id": user.company_id.id,
                    "name": user.name,
                    "user_id": user.id,
                    "tz": user.tz,
                }
                for user in cls.staff_users
            ]
        )
        cls.staff_users_employees = cls.env["hr.employee"].create(
            [
                {
                    "company_id": user.company_id.id,
                    "resource_calendar_id": cls.test_calendar.id,
                    "resource_id": cls.staff_users_resources[user_idx].id,
                }
                for user_idx, user in enumerate(cls.staff_users)
            ]
        )

        cls.test_events = (
            cls.env["calendar.event"]
            .with_context(cls._test_context)
            .create(
                [
                    {
                        "attendee_ids": [(0, 0, {"partner_id": user.partner_id.id})],
                        "name": "Event for %s" % user.name,
                        "partner_ids": [(4, user.partner_id.id)],
                        "start": cls.reference_monday
                        + timedelta(weeks=week_idx, days=day_idx, hours=(user_idx / 4)),
                        "stop": cls.reference_monday
                        + timedelta(
                            weeks=week_idx, days=day_idx, hours=(user_idx / 4) + 1
                        ),
                        "user_id": user.id,
                    }
                    for day_idx in range(5)
                    for week_idx in range(5)
                    for user_idx, user in enumerate(cls.staff_users)
                ]
            )
        )
        cls.test_leaves = (
            cls.env["resource.schedule.exception"]
            .with_context(cls._test_context)
            .create(
                [
                    {
                        "calendar_id": user.resource_calendar_id.id,
                        "company_id": user.company_id.id,
                        "date_from": cls.reference_monday
                        + timedelta(weeks=week_idx * 2, days=(user_idx / 4), hours=2),
                        "date_to": cls.reference_monday
                        + timedelta(weeks=week_idx * 2, days=(user_idx / 4), hours=8),
                        "name": "Leave for %s" % user.name,
                        "resource_id": user.resource_ids[0].id,
                    }
                    for week_idx in range(5)
                    for user_idx, user in enumerate(cls.staff_users)
                ]
            )
        )

        cls.test_apt_type = cls.env[
            "appointment.type"
        ].create(
            {
                "appointment_tz": "Europe/Brussels",
                "appointment_duration": 1,
                "category": "recurring",
                "is_auto_assign": True,
                "is_published": True,
                "max_schedule_days": 60,
                "min_cancellation_hours": 1,
                "min_schedule_hours": 1,
                "name": "Test Appointment Type",
                "schedule_based_on": "users",
                "slot_ids": [
                    (
                        0,
                        0,
                        {
                            "end_hour": hour + 1,
                            "start_hour": hour,
                            "weekday": weekday,
                        },
                    )
                    for weekday in ["1", "2", "3", "4", "5"]
                    for hour in range(8, 16)
                ],
                "staff_user_ids": [(4, user.id) for user in cls.staff_users],
                "work_hours_activated": True,
            }
        )
        cls.test_appointment_location = cls.env["res.partner"].create(
            {"name": "Bxls Office", "street": "Rue Haute 63"}
        )


@tagged("appointment_performance", "post_install", "-at_install")
class AppointmentPerformanceTest(AppointmenHrPerformanceCase):
    def setUp(self):
        super().setUp()
        self.flush_tracking()

    def test_appointment_initial_values(self):
        self.assertEqual(len(self.test_apt_type.slot_ids), 40)
        self.assertTrue(
            all(employee.resource_id for employee in self.staff_users_employees)
        )
        self.assertTrue(
            all(
                employee.resource_id.calendar_id
                for employee in self.staff_users_employees
            )
        )
        self.assertTrue(
            all(employee.user_id for employee in self.staff_users_employees)
        )

    @users("staff_user_bxls")
    def test_get_appointment_slots_anytime(self):
        self.apt_type_bxls_2days.write(
            {
                "category": "anytime",
                "max_schedule_days": 90,
                "slot_ids": [(5, 0)]
                + [
                    (
                        0,
                        0,
                        {
                            "end_hour": 0,
                            "start_hour": hour * 0.5,
                            "weekday": str(day + 1),
                        },
                    )
                    for hour in range(2)
                    for day in range(7)
                ],
                "staff_user_ids": [(5, 0), (4, self.env.uid)],
                "work_hours_activated": True,
            }
        )
        self.env.flush_all()
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=38):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        global_slots_enddate = date(2022, 6, 4)
        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "March 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "April 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "May 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @users("staff_user_bxls")
    def test_get_appointment_slots_anytime_short(self):
        self.apt_type_bxls_2days.write(
            {
                "category": "anytime",
                "max_schedule_days": 10,
                "slot_ids": [(5, 0)]
                + [
                    (
                        0,
                        0,
                        {
                            "end_hour": 0,
                            "start_hour": hour * 0.5,
                            "weekday": str(day + 1),
                        },
                    )
                    for hour in range(2)
                    for day in range(7)
                ],
                "staff_user_ids": [(5, 0), (4, self.env.uid)],
                "work_hours_activated": True,
            }
        )
        self.env.flush_all()
        apt_type = self.apt_type_bxls_2days.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=38):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @warmup
    @users("staff_user_bxls")
    def test_get_appointment_slots_custom(self):
        apt_type_custom_bxls = (
            self.env["appointment.type"]
            .sudo()
            .create(
                {
                    "appointment_tz": "Europe/Brussels",
                    "appointment_duration": 1,
                    "category": "custom",
                    "is_auto_assign": True,
                    "location_id": self.test_appointment_location.id,
                    "name": "Bxls Appt Type",
                    "min_cancellation_hours": 1,
                    "min_schedule_hours": 1,
                    "max_schedule_days": 30,
                    "slot_ids": [
                        (
                            0,
                            0,
                            {
                                "end_datetime": self.reference_monday
                                + timedelta(days=day, hours=hour + 1),
                                "start_datetime": self.reference_monday
                                + timedelta(days=day, hours=hour),
                                "slot_type": "unique",
                                "weekday": "1",
                            },
                        )
                        for day in range(30)
                        for hour in range(8, 16)
                    ],
                    "staff_user_ids": [(4, self.env.uid)],
                    "work_hours_activated": False,
                }
            )
        )
        self.flush_tracking()
        apt_type_custom_bxls = apt_type_custom_bxls.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=7):
            t0 = time.time()
            res = apt_type_custom_bxls._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        global_slots_enddate = date(2022, 4, 2)
        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "March 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @warmup
    @users("staff_user_bxls")
    def test_get_appointment_slots_custom_whours(self):
        apt_type_custom_bxls = (
            self.env["appointment.type"]
            .sudo()
            .create(
                {
                    "appointment_tz": "Europe/Brussels",
                    "appointment_duration": 1,
                    "category": "custom",
                    "is_auto_assign": True,
                    "location_id": self.test_appointment_location.id,
                    "name": "Bxls Appt Type",
                    "min_cancellation_hours": 1,
                    "min_schedule_hours": 1,
                    "max_schedule_days": 30,
                    "slot_ids": [
                        (
                            0,
                            0,
                            {
                                "end_datetime": self.reference_monday
                                + timedelta(days=day, hours=hour + 1),
                                "start_datetime": self.reference_monday
                                + timedelta(days=day, hours=hour),
                                "slot_type": "unique",
                                "weekday": "1",
                            },
                        )
                        for day in range(30)
                        for hour in range(8, 16)
                    ],
                    "staff_user_ids": [(4, self.env.uid)],
                    "work_hours_activated": True,
                }
            )
        )
        self.flush_tracking()
        apt_type_custom_bxls = apt_type_custom_bxls.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=7):
            t0 = time.time()
            res = apt_type_custom_bxls._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        global_slots_enddate = date(2022, 4, 2)
        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "March 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @users("staff_user_bxls")
    def test_get_appointment_slots_website(self):
        random.seed(1871)
        self.test_apt_type.write({"work_hours_activated": False})
        apt_type = self.test_apt_type.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=48):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        global_slots_enddate = date(2022, 4, 30)
        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "March 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "April 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": global_slots_enddate,
                "slots_duration": 1,
                "slots_hours": range(8, 16, 1),
                "slots_startdt": self.reference_monday,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @users("staff_user_bxls")
    def test_get_appointment_slots_website_whours(self):
        random.seed(1871)
        apt_type = self.test_apt_type.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=61):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        global_slots_enddate = date(2022, 4, 30)
        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "March 2022",
                    "weeks_count": 5,
                },
                {
                    "name_formated": "April 2022",
                    "weeks_count": 5,
                },
            ],
            {
                "enddate": global_slots_enddate,
                "slots_duration": 1,
                "slots_hours": range(8, 16, 1),
                "slots_startdt": self.reference_monday,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @users("staff_user_bxls")
    def test_get_appointment_slots_website_whours_short(self):
        random.seed(1871)
        self.test_apt_type.write({"max_schedule_days": 10})
        self.env.flush_all()
        apt_type = self.test_apt_type.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=59):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )

    @warmup
    @users("staff_user_bxls")
    def test_get_appointment_slots_website_whours_short_warmup(self):
        random.seed(1871)
        self.test_apt_type.write({"max_schedule_days": 10})
        self.env.flush_all()
        apt_type = self.test_apt_type.with_user(self.env.user)

        with self.mockAppointmentCalls(), self.assertQueryCount(staff_user_bxls=32):
            t0 = time.time()
            res = apt_type._get_appointment_slots(
                "Europe/Brussels", reference_date=self.reference_now
            )
            t1 = time.time()

        _logger.info("Called _get_appointment_slots, time %.3f", t1 - t0)
        _logger.info(
            "Called methods\nSearch calendar event called %s\n"
            "Search count calendar event called %s\n"
            "Partner calendar check called %s\n"
            "Resource Calendar work intervals batch called %s",
            self._mock_calevent_search.call_count,
            self._mock_calevent_search_count.call_count,
            self._mock_partner_calendar_check.call_count,
            self._mock_cal_work_intervals.call_count,
        )

        self.assertSlots(
            res,
            [
                {
                    "name_formated": "February 2022",
                    "weeks_count": 5,
                }
            ],
            {
                "enddate": self.global_slots_enddate,
                "startdate": self.reference_now_monthweekstart,
            },
        )


@tagged("appointment_performance", "post_install", "-at_install")
class OnlineAppointmentPerformance(
    AppointmentUIPerformanceCase, AppointmenHrPerformanceCase
):
    def setUp(self):
        super().setUp()

        if "product.pricelist" in self.env:
            self.env["product.pricelist"].search([]).write({"active": False})

        self.flush_tracking()

    @warmup
    def test_appointment_type_page_anytime(self):
        random.seed(1871)

        self.test_apt_type.write(
            {
                "category": "anytime",
                "max_schedule_days": 90,
                "slot_ids": [(5, 0)]
                + [
                    (
                        0,
                        0,
                        {
                            "end_hour": 0,
                            "start_hour": hour * 0.5,
                            "weekday": str(day + 1),
                        },
                    )
                    for hour in range(2)
                    for day in range(7)
                ],
                "staff_user_ids": [(5, 0), (4, self.staff_users[0].id)],
            }
        )
        self.env.flush_all()

        t0 = time.time()
        with freeze_time(self.reference_now):
            self.authenticate("staff_user_bxls", "staff_user_bxls")
            with self.assertQueryCount(default=55):
                self._test_url_open("/appointment/%i" % self.test_apt_type.id)
        t1 = time.time()

        _logger.info(
            "Browsed /appointment/%i, time %.3f", self.test_apt_type.id, t1 - t0
        )

    @warmup
    def test_appointment_type_page_website_whours_user(self):
        random.seed(1871)

        t0 = time.time()
        with freeze_time(self.reference_now):
            self.authenticate("staff_user_bxls", "staff_user_bxls")
            with self.assertQueryCount(default=53):
                self._test_url_open("/appointment/%i" % self.test_apt_type.id)
        t1 = time.time()

        _logger.info(
            "Browsed /appointment/%i, time %.3f", self.test_apt_type.id, t1 - t0
        )
