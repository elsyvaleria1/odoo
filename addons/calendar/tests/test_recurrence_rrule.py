from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import rrule

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.base.models.mixin_recurrence_rule import WEEKDAY_SELECTION


class TestRecurrenceWeekStart(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")
        cls.sunday_user = new_test_user(
            cls.env, login="rr_sunday", lang="en_US", tz="UTC"
        )
        cls.monday_user = new_test_user(
            cls.env, login="rr_monday", lang="fr_FR", tz="UTC"
        )

    def test_a_user_without_a_language_still_gets_a_real_week_start(self):
        user = new_test_user(self.env, login="rrule_no_lang")
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_partner SET lang = NULL WHERE id = %s", [user.partner_id.id]
        )
        self.env.invalidate_all()
        self.assertFalse(user.lang)

        week_start = (
            self.env["calendar.recurrence"].with_user(user)._default_week_start()
        )

        self.assertIn(week_start, dict(WEEKDAY_SELECTION))

    def _create_biweekly_sunday_monday(self, user, count):
        return (
            self.env["calendar.event"]
            .with_user(user)
            .create(
                {
                    "name": "Biweekly",
                    "start": datetime(2024, 1, 7, 10, 0),
                    "stop": datetime(2024, 1, 7, 11, 0),
                    "recurrency": True,
                    "repeat_unit": "week",
                    "repeat_interval": 2,
                    "sun": True,
                    "mon": True,
                    "repeat_type": "count",
                    "repeat_number": count,
                    "event_tz": "UTC",
                    "partner_ids": [
                        Command.link(self.sunday_user.partner_id.id),
                        Command.link(self.monday_user.partner_id.id),
                    ],
                }
            )
        )

    def _dates(self, recurrence):
        return [
            event.start.date()
            for event in recurrence.calendar_event_ids.sorted("start")
        ]

    def test_a_series_keeps_its_creator_week_start_when_another_user_edits_it(self):
        event = self._create_biweekly_sunday_monday(self.sunday_user, 4)
        self.assertEqual(
            self._dates(event.recurrence_id),
            [date(2024, 1, 7), date(2024, 1, 8), date(2024, 1, 21), date(2024, 1, 22)],
        )

        event.with_user(self.monday_user).write(
            {"recurrence_update": "all", "repeat_number": 5}
        )

        recurrence = event.recurrence_id
        self.assertEqual(
            self._dates(recurrence),
            [
                date(2024, 1, 7),
                date(2024, 1, 8),
                date(2024, 1, 21),
                date(2024, 1, 22),
                date(2024, 2, 4),
            ],
        )
        self.assertEqual(recurrence.week_start, "SUN")
        self.assertIn("WKST=SU", recurrence.rrule)


LAST_WEEKDAY = "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=6"
LAST_WEEKDAY_PATTERN = "FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO,TU,WE,TH,FR"


class TestRecurrenceCustomRule(TransactionCase):
    def _series(self, rule, start):
        event = self.env["calendar.event"].create(
            {
                "name": "Custom",
                "start": start,
                "stop": start + timedelta(hours=1),
                "recurrency": True,
                "rrule": rule,
                "event_tz": "UTC",
            }
        )
        return event.recurrence_id

    def _starts(self, recurrence):
        return recurrence.calendar_event_ids.sorted("start").mapped("start")

    def _rule_starts(self, rule, start):
        return list(rrule.rrulestr(rule, dtstart=start))

    def test_the_last_weekday_from_january_31_falls_in_every_month(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))

        self.assertEqual(recurrence.custom_rrule, LAST_WEEKDAY_PATTERN)
        self.assertEqual(
            [start.date() for start in self._starts(recurrence)],
            [
                date(2024, 1, 31),
                date(2024, 2, 29),
                date(2024, 3, 29),
                date(2024, 4, 30),
                date(2024, 5, 31),
                date(2024, 6, 28),
            ],
        )
        self.assertTrue(recurrence.name.startswith("Custom rule"))

    def test_a_rule_the_options_cannot_hold_is_kept_whole(self):
        for rule, start in (
            (LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0)),
            (
                "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=1,-1;COUNT=4",
                datetime(2024, 1, 1, 10, 0),
            ),
            ("FREQ=MONTHLY;BYDAY=1MO,3MO;COUNT=4", datetime(2024, 1, 1, 10, 0)),
            (
                "FREQ=MONTHLY;INTERVAL=2;BYDAY=MO,WE;COUNT=4",
                datetime(2024, 1, 1, 10, 0),
            ),
            (
                "FREQ=DAILY;INTERVAL=3;BYDAY=MO,TU,WE,TH,FR;COUNT=5",
                datetime(2024, 1, 1, 10, 0),
            ),
        ):
            with self.subTest(rule=rule):
                recurrence = self._series(rule, start)
                self.assertTrue(recurrence.custom_rrule)
                self.assertEqual(
                    self._starts(recurrence), self._rule_starts(rule, start)
                )
                self.assertEqual(
                    self._rule_starts(recurrence._rrule_serialize(), start),
                    self._rule_starts(rule, start),
                )

    def test_a_rule_the_options_hold_is_not_custom(self):
        for rule, start in (
            ("FREQ=WEEKLY;COUNT=3;BYDAY=WE", datetime(2024, 1, 3, 10, 0)),
            ("FREQ=MONTHLY;BYDAY=MO,WE;COUNT=4", datetime(2024, 1, 1, 10, 0)),
            ("FREQ=MONTHLY;COUNT=3;BYMONTHDAY=-1", datetime(2024, 1, 31, 10, 0)),
            ("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1;COUNT=3", datetime(2024, 1, 1, 10, 0)),
        ):
            with self.subTest(rule=rule):
                recurrence = self._series(rule, start)
                self.assertFalse(recurrence.custom_rrule)
                self.assertEqual(
                    self._starts(recurrence), self._rule_starts(rule, start)
                )

    def test_ending_a_custom_series_keeps_its_rule(self):
        start = datetime(2024, 1, 31, 10, 0)
        recurrence = self._series(LAST_WEEKDAY, start)

        recurrence.write({"repeat_type": "until", "repeat_until": date(2024, 4, 30)})

        self.assertEqual(recurrence.custom_rrule, LAST_WEEKDAY_PATTERN)
        self.assertEqual(
            [start.date() for start in self._rule_starts(recurrence.rrule, start)],
            [
                date(2024, 1, 31),
                date(2024, 2, 29),
                date(2024, 3, 29),
                date(2024, 4, 30),
            ],
        )

    def test_a_series_wide_edit_keeps_its_custom_rule(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))
        event = recurrence.base_event_id

        event.write({"recurrence_update": "all", "repeat_number": 3})

        self.assertEqual(event.recurrence_id.custom_rrule, LAST_WEEKDAY_PATTERN)
        self.assertEqual(
            self._starts(event.recurrence_id),
            [
                datetime(2024, 1, 31, 10, 0),
                datetime(2024, 2, 29, 10, 0),
                datetime(2024, 3, 29, 10, 0),
            ],
        )

    def test_moving_the_following_events_keeps_their_custom_rule(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))
        third = recurrence.calendar_event_ids.sorted("start")[2]

        third.write(
            {
                "recurrence_update": "subsequent",
                "start": datetime(2024, 3, 29, 11, 0),
                "stop": datetime(2024, 3, 29, 12, 0),
            }
        )

        self.assertEqual(third.recurrence_id.custom_rrule, LAST_WEEKDAY_PATTERN)
        self.assertEqual(
            self._starts(third.recurrence_id),
            [
                datetime(2024, 3, 29, 11, 0),
                datetime(2024, 4, 30, 11, 0),
                datetime(2024, 5, 31, 11, 0),
                datetime(2024, 6, 28, 11, 0),
            ],
        )

    def test_editing_an_option_converts_the_series(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))
        event = recurrence.base_event_id

        event.write({"recurrence_update": "all", "repeat_interval": 2})

        self.assertFalse(event.recurrence_id.custom_rrule)
        self.assertEqual(
            event.recurrence_id.rrule, "FREQ=MONTHLY;INTERVAL=2;COUNT=6;BYMONTHDAY=31"
        )

    def test_editing_an_option_of_the_rule_converts_it(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))

        recurrence.write({"day": 15})

        self.assertFalse(recurrence.custom_rrule)
        self.assertEqual(recurrence.rrule, "FREQ=MONTHLY;COUNT=6;BYMONTHDAY=15")

    def test_simplifying_a_custom_series_follows_its_options(self):
        recurrence = self._series(LAST_WEEKDAY, datetime(2024, 1, 31, 10, 0))
        event = recurrence.base_event_id

        event.action_simplify_recurrence()

        self.assertFalse(event.recurrence_id.custom_rrule)
        self.assertEqual(
            event.recurrence_id.rrule, "FREQ=MONTHLY;COUNT=6;BYMONTHDAY=31"
        )
        self.assertEqual(
            [start.date() for start in self._starts(event.recurrence_id)],
            [
                date(2024, 1, 31),
                date(2024, 3, 31),
                date(2024, 5, 31),
                date(2024, 7, 31),
                date(2024, 8, 31),
                date(2024, 10, 31),
            ],
        )


@tagged("post_install", "-at_install")
class TestRecurrenceRruleOccurrences(TransactionCase):
    def _timed(self, values):
        start = datetime(2026, 1, 1, 10, 0)
        return self.env["calendar.recurrence"].new(
            {
                **values,
                "calendar_event_ids": [
                    Command.create(
                        {
                            "name": "Timed",
                            "start": start,
                            "stop": start + timedelta(hours=1),
                        }
                    )
                ],
            }
        )

    def _local_dates(self, recurrence, start, tz):
        return [
            occurrence.replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).date()
            for occurrence, _stop in sorted(
                recurrence._range_calculation(start, timedelta(hours=1))
            )
        ]

    def test_repeating_until_no_date_is_refused_as_a_user_error(self):
        rule = self.env["calendar.recurrence"].new(
            {
                "repeat_interval": 1,
                "repeat_unit": "day",
                "repeat_type": "until",
                "repeat_until": False,
            }
        )
        with self.assertRaises(UserError):
            rule._rrule_serialize()

    def test_an_east_of_utc_bimonthly_rule_starts_on_its_first_local_date(self):
        recurrence = self._timed(
            {
                "event_tz": "Asia/Tokyo",
                "repeat_unit": "month",
                "repeat_interval": 2,
                "month_by": "date",
                "day": 1,
                "repeat_type": "count",
                "repeat_number": 3,
            }
        )
        self.assertEqual(
            self._local_dates(recurrence, datetime(2026, 9, 30, 20, 0), "Asia/Tokyo"),
            [date(2026, 10, 1), date(2026, 12, 1), date(2027, 2, 1)],
        )

    def test_an_east_of_utc_biweekly_rule_starts_on_its_first_local_date(self):
        recurrence = self._timed(
            {
                "event_tz": "Asia/Tokyo",
                "repeat_unit": "week",
                "repeat_interval": 2,
                "sun": True,
                "week_start": "SUN",
                "repeat_type": "count",
                "repeat_number": 3,
            }
        )
        local_dates = self._local_dates(
            recurrence, datetime(2026, 10, 3, 16, 0), "Asia/Tokyo"
        )
        self.assertEqual(
            local_dates, [date(2026, 10, 4), date(2026, 10, 18), date(2026, 11, 1)]
        )

    def test_an_occurrence_on_a_repeated_wall_hour_reads_as_standard_time(self):
        recurrence = self._timed(
            {
                "event_tz": "America/New_York",
                "repeat_unit": "day",
                "repeat_interval": 1,
                "repeat_type": "count",
                "repeat_number": 2,
            }
        )
        starts = sorted(
            start
            for start, _stop in recurrence._range_calculation(
                datetime(2026, 10, 31, 5, 30), timedelta(hours=1)
            )
        )
        self.assertEqual(
            starts, [datetime(2026, 10, 31, 5, 30), datetime(2026, 11, 1, 6, 30)]
        )

    def test_a_utc_until_is_read_as_the_recurrence_local_date(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=WEEKLY;UNTIL=20200120T055959Z;BYDAY=MO",
            datetime(2020, 1, 6, 16, 0),
            ZoneInfo("America/Mexico_City"),
        )
        self.assertEqual(values["repeat_until"], date(2020, 1, 19))
        self.assertEqual(values["repeat_type"], "until")

    def test_a_monthly_setpos_rule_stays_the_nth_weekday_of_the_month(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1;COUNT=3", datetime(2020, 1, 6, 16, 0)
        )
        self.assertEqual(values["repeat_unit"], "month")
        self.assertEqual(values["month_by"], "day")
        self.assertEqual(values["weekday"], "MON")
        self.assertEqual(values["byday"], "1")
        self.assertNotIn("mon", values)

    def test_an_implicit_weekday_is_the_local_start_weekday(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=WEEKLY;COUNT=5",
            datetime(2024, 1, 16, 2, 0),
            ZoneInfo("America/Mexico_City"),
        )
        self.assertTrue(values["mon"])
        self.assertFalse(values["tue"])

    def test_an_implicit_month_day_is_the_local_start_day(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=MONTHLY;COUNT=5",
            datetime(2024, 1, 16, 2, 0),
            ZoneInfo("America/Mexico_City"),
        )
        self.assertEqual((values["month_by"], values["day"]), ("date", 15))

    def test_an_implicit_weekday_is_the_local_start_weekday_under_a_utc_until(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=WEEKLY;UNTIL=20240301T055959Z",
            datetime(2024, 1, 16, 2, 0),
            ZoneInfo("America/Mexico_City"),
        )
        self.assertTrue(values["mon"])
        self.assertFalse(values["tue"])
        self.assertEqual(values["repeat_until"], date(2024, 2, 29))

    def test_an_implicit_weekday_of_an_allday_start_is_its_own_date(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=WEEKLY;COUNT=3",
            datetime(2024, 1, 15, 8, 0),
            ZoneInfo("Pacific/Honolulu"),
            allday=True,
        )
        self.assertTrue(values["mon"])
        self.assertFalse(values["sun"])

    def test_a_monthly_rule_on_every_listed_weekday_is_weekly(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=MONTHLY;BYDAY=MO,WE;COUNT=4", datetime(2024, 1, 1, 16, 0)
        )
        self.assertEqual(values["repeat_unit"], "week")
        self.assertTrue(values["mon"] and values["wed"])

    def test_a_monthly_rule_no_weekly_rule_can_hold_stays_monthly(self):
        Rrule = self.env["calendar.recurrence"]
        for rule, pattern in (
            (
                "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=6",
                "FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO,TU,WE,TH,FR",
            ),
            (
                "FREQ=MONTHLY;INTERVAL=2;BYDAY=MO,WE",
                "FREQ=MONTHLY;INTERVAL=2;BYDAY=MO,WE",
            ),
        ):
            with self.subTest(rule=rule):
                values = Rrule._rrule_parse(rule, datetime(2024, 1, 31, 16, 0))
                self.assertEqual(values["repeat_unit"], "month")
                self.assertEqual((values["month_by"], values["day"]), ("date", 31))
                self.assertNotIn("mon", values)
                self.assertEqual(values["custom_rrule"], pattern)

    def test_a_yearly_rule_stays_yearly(self):
        Rrule = self.env["calendar.recurrence"]
        for rule, pattern in (
            ("FREQ=YEARLY", None),
            ("FREQ=YEARLY;BYMONTH=4;BYDAY=2SU", "FREQ=YEARLY;BYMONTH=4;BYDAY=+2SU"),
            ("FREQ=YEARLY;BYDAY=2SU", "FREQ=YEARLY;BYDAY=+2SU"),
        ):
            with self.subTest(rule=rule):
                values = Rrule._rrule_parse(rule, datetime(2020, 3, 8, 16, 0))
                self.assertEqual(values["repeat_unit"], "year")
                self.assertEqual(values["month_by"], "date")
                self.assertNotIn("weekday", values)
                self.assertEqual(values["custom_rrule"], pattern)


@tagged("post_install", "-at_install")
class TestRecurrenceRruleMonthEdges(TransactionCase):
    def _rule(self, **values):
        return self.env["calendar.recurrence"].new(
            {"repeat_interval": 1, "repeat_type": "count", **values}
        )

    def _dates(self, recurrence, start):
        return [
            occurrence.date()
            for occurrence, _stop in sorted(
                recurrence._range_calculation(start, timedelta(hours=1))
            )
        ]

    def test_the_last_day_of_the_month_is_parsed(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=MONTHLY;COUNT=12;BYMONTHDAY=-1", datetime(2024, 1, 31, 16, 0)
        )
        self.assertEqual(values["repeat_unit"], "month")
        self.assertEqual(values["month_by"], "date")
        self.assertEqual(values["day"], -1)

    def test_the_last_day_of_the_month_is_serialised(self):
        recurrence = self._rule(
            repeat_unit="month", month_by="date", day=-1, repeat_number=12
        )
        self.assertEqual(
            recurrence._rrule_serialize(), "FREQ=MONTHLY;COUNT=12;BYMONTHDAY=-1"
        )

    def test_the_last_day_of_the_month_falls_on_each_month_end(self):
        recurrence = self._rule(
            event_tz="UTC",
            repeat_unit="month",
            month_by="date",
            day=-1,
            repeat_number=13,
        )
        self.assertEqual(
            self._dates(recurrence, datetime(2024, 1, 31, 16, 0)),
            [
                date(2024, 1, 31),
                date(2024, 2, 29),
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 31),
                date(2024, 6, 30),
                date(2024, 7, 31),
                date(2024, 8, 31),
                date(2024, 9, 30),
                date(2024, 10, 31),
                date(2024, 11, 30),
                date(2024, 12, 31),
                date(2025, 1, 31),
            ],
        )

    def test_the_last_day_of_the_month_is_named(self):
        recurrence = self._rule(
            repeat_unit="month", month_by="date", day=-1, repeat_number=12
        )
        self.assertEqual(
            recurrence.get_recurrence_name(),
            "Every 1 Months on the last day for 12 events",
        )

    def test_a_yearly_nth_weekday_is_parsed_in_its_start_month(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=YEARLY;COUNT=3;BYMONTH=3;BYDAY=2SU", datetime(2024, 3, 10, 16, 0)
        )
        self.assertEqual(values["repeat_unit"], "year")
        self.assertEqual(values["month_by"], "day")
        self.assertEqual(values["weekday"], "SUN")
        self.assertEqual(values["byday"], "2")

    def test_a_yearly_nth_weekday_month_is_the_local_start_month(self):
        values = self.env["calendar.recurrence"]._rrule_parse(
            "FREQ=YEARLY;BYMONTH=3;BYDAY=1SU",
            datetime(2024, 2, 29, 20, 0),
            ZoneInfo("Asia/Tokyo"),
        )
        self.assertEqual(values["month_by"], "day")
        self.assertEqual(values["weekday"], "SUN")
        self.assertEqual(values["byday"], "1")

    def test_a_yearly_nth_weekday_is_serialised_with_its_month(self):
        recurrence = self._rule(
            repeat_unit="year",
            month_by="day",
            weekday="SUN",
            byday="2",
            repeat_number=3,
        )
        self.assertEqual(
            recurrence._rrule_value(
                str(recurrence._get_rrule(dtstart=datetime(2024, 3, 10), bounded=False))
            ),
            "FREQ=YEARLY;COUNT=3;BYMONTH=3;BYDAY=+2SU",
        )
        values = recurrence._rrule_parse(
            "FREQ=YEARLY;COUNT=3;BYMONTH=3;BYDAY=+2SU", datetime(2024, 3, 10, 16, 0)
        )
        self.assertEqual(
            (values["month_by"], values["weekday"], values["byday"]),
            ("day", "SUN", "2"),
        )

    def test_a_yearly_nth_weekday_repeats_on_that_weekday(self):
        recurrence = self._rule(
            event_tz="UTC",
            repeat_unit="year",
            month_by="day",
            weekday="SUN",
            byday="2",
            repeat_number=3,
        )
        self.assertEqual(
            self._dates(recurrence, datetime(2024, 3, 10, 16, 0)),
            [date(2024, 3, 10), date(2025, 3, 9), date(2026, 3, 8)],
        )

    def test_a_yearly_rule_on_its_start_date_ignores_the_weekday(self):
        recurrence = self._rule(
            event_tz="UTC",
            repeat_unit="year",
            month_by="date",
            weekday="SUN",
            byday="2",
            repeat_number=3,
        )
        self.assertEqual(
            self._dates(recurrence, datetime(2024, 3, 10, 16, 0)),
            [date(2024, 3, 10), date(2025, 3, 10), date(2026, 3, 10)],
        )
