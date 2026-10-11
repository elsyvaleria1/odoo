from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.libs.datetime import timezone, to_timezone
from odoo.tests import freeze_time, tagged

from .common import HrPresenceCase


@tagged("post_install", "-at_install")
class TestPresenceState(HrPresenceCase):
    def test_the_module_rule_reads_as_one_function(self):
        employee = self._make_employee("readable")
        today = self._today_for(employee)
        working = frozenset([employee.id])
        self.assertEqual(employee._hr_presence_verdict(today, working), "absent")
        self.assertEqual(
            employee._hr_presence_verdict(today, frozenset()), "out_of_working_hour"
        )
        employee.hr_presence_ip_date = today
        self.assertEqual(employee._hr_presence_verdict(today, working), "present")

    def test_an_employee_at_work_with_no_sign_of_activity_is_absent(self):
        truant = self._make_employee("truant")
        self.assertFalse(truant.is_absent)
        self.assertIn(
            truant.id,
            truant._get_employee_ids_working_now(),
            "fixture: the employee must be inside working hours",
        )
        self.assertEqual(truant.hr_presence_state, "absent")

    def test_an_approved_time_off_excuses_the_absence(self):
        excused = self._make_employee("excused")
        self.assertEqual(
            self._verdict(excused),
            "absent",
            "fixture: without the leave this employee is absentable, so the "
            "verdict below tests the leave and not the schedule",
        )
        self._approve_leave(excused)
        excused.invalidate_recordset()
        self.assertTrue(excused.is_absent)
        self.assertEqual(self._verdict(excused), "out_of_working_hour")

    def test_a_flexible_employee_is_never_absent_from_hours_they_choose(self):
        flexible = self.env["resource.calendar"].create(
            {
                "name": "flexible",
                "tz": "UTC",
                "company_id": self.company.id,
                "schedule_type": "flexible",
                "attendance_ids": [(5, 0, 0)],
            }
        )
        employee = self._make_employee("flexible", calendar=flexible)
        self.assertTrue(employee.resource_id._is_flexible())
        self.assertEqual(self._verdict(employee), "out_of_working_hour")
        self.assertNotEqual(employee.hr_presence_state, "absent")

    def test_a_fully_flexible_employee_is_never_absent_either(self):
        employee = self._make_employee("no_calendar")
        employee.resource_calendar_id = False
        employee.invalidate_recordset()
        self.assertTrue(employee.resource_id._is_fully_flexible())
        self.assertEqual(self._verdict(employee), "out_of_working_hour")

    def test_a_flexible_employee_can_still_be_present(self):
        flexible = self.env["resource.calendar"].create(
            {
                "name": "flexible present",
                "tz": "UTC",
                "company_id": self.company.id,
                "schedule_type": "flexible",
                "attendance_ids": [(5, 0, 0)],
            }
        )
        employee = self._make_employee("flexible_present", calendar=flexible)
        employee.hr_presence_ip_date = self._today_for(employee)
        self.assertEqual(self._verdict(employee), "present")

    def test_an_employee_outside_working_hours_is_off_hours_not_absent(self):
        company = self.env["res.company"].create({"name": "Night Co"})
        calendar = self._make_calendar(company, "UTC", hour_from=0.0, hour_to=0.01)
        company.write(
            {
                "resource_calendar_id": calendar.id,
                "hr_presence_control_ip": True,
                "hr_presence_control_ip_list": "10.0.0.1",
            }
        )
        sleeper = self._make_employee("sleeper", company=company, calendar=calendar)
        self.assertEqual(
            sleeper.resource_calendar_id,
            calendar,
            "fixture: an employee with no calendar is off-hours for another reason",
        )
        self.assertFalse(sleeper.resource_id._is_flexible())
        self.assertEqual(sleeper.hr_presence_state, "out_of_working_hour")

    def test_ip_evidence_of_today_makes_an_employee_present(self):
        connected = self._make_employee("connected")
        connected.hr_presence_ip_date = self._today_for(connected)
        self.assertEqual(connected.hr_presence_state, "present")

    def test_evidence_of_a_previous_day_does_not_carry_over(self):
        stale = self._make_employee("stale")
        stale.hr_presence_ip_date = self._today_for(stale) - timedelta(days=1)
        self.assertEqual(stale.hr_presence_state, "absent")

    def test_an_archived_employee_keeps_the_archive_state(self):
        gone = self._make_employee("gone")
        gone.action_archive()
        gone.invalidate_recordset()
        self.assertEqual(gone.hr_presence_state, "archive")

    def test_the_state_moves_when_the_evidence_moves(self):
        employee = self._make_employee("watched")
        self.assertEqual(employee.hr_presence_state, "absent")
        employee.hr_presence_ip_date = self._today_for(employee)
        self.assertEqual(employee.hr_presence_state, "present")
        employee.hr_presence_ip_date = False
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_a_company_with_no_control_ignores_the_evidence_entirely(self):
        plain = self.env["res.company"].create({"name": "Plain Co"})
        calendar = self._make_calendar(plain, "UTC")
        plain.resource_calendar_id = calendar
        employee = self._make_employee("plain", company=plain, calendar=calendar)
        before = employee.hr_presence_state
        employee.hr_presence_ip_date = self._today_for(employee)
        employee.invalidate_recordset()
        self.assertEqual(
            employee.hr_presence_state,
            before,
            "this module must not decide for a company that asked it not to",
        )


@tagged("post_install", "-at_install")
class TestManualOverride(HrPresenceCase):
    def test_a_manager_sets_the_presence_for_the_day(self):
        employee = self._make_employee("overridden")
        employee.with_user(self.manager).action_set_present()
        self.assertEqual(employee.hr_presence_manual_state, "present")
        self.assertEqual(employee.hr_presence_state, "present")
        employee.with_user(self.manager).action_set_absent()
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_an_override_expires_with_the_day_it_was_made_for(self):
        employee = self._make_employee("yesterdays")
        employee.write(
            {
                "hr_presence_manual_state": "present",
                "hr_presence_manual_date": self._today_for(employee)
                - timedelta(days=1),
            }
        )
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_an_override_outranks_the_evidence(self):
        employee = self._make_employee("vetoed")
        employee.hr_presence_ip_date = self._today_for(employee)
        employee.with_user(self.manager).action_set_absent()
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_the_sweep_does_not_turn_an_automatic_present_into_a_manual_one(self):
        employee = self._make_employee("automatic")
        employee.hr_presence_ip_date = self._today_for(employee)
        self.env["hr.employee"]._check_presence()
        self.assertEqual(employee.hr_presence_state_display, "present")
        self.assertFalse(employee.hr_presence_manual_state)

    def test_only_an_hr_manager_may_act(self):
        employee = self._make_employee("guarded")
        plain_user = self._make_user("plain_actor", self.company)
        self.assertFalse(
            plain_user.has_group("hr.group_hr_manager"),
            "fixture: the actor must not be a manager, or the guard has nothing "
            "to refuse -- res.users.group_ids has a default, and on a demo "
            "database it includes hr.group_hr_manager",
        )
        for action in (
            "action_set_present",
            "action_set_absent",
            "action_send_log",
            "action_send_sms",
            "action_send_email",
        ):
            with self.subTest(action=action), self.assertRaises(UserError):
                getattr(employee.with_user(plain_user), action)()


@tagged("post_install", "-at_install")
class TestEmailEvidence(HrPresenceCase):
    def test_enough_emails_sent_today_prove_presence(self):
        writer = self._make_employee("writer")
        self._post_emails(writer, 2)
        self.env["hr.employee"]._check_presence()
        self.assertEqual(writer.hr_presence_email_date, self._today_for(writer))
        self.assertEqual(writer.hr_presence_state, "present")

    def test_fewer_emails_than_the_threshold_prove_nothing(self):
        writer = self._make_employee("shy")
        posted = self._post_emails(writer, 1)
        self._assert_authored(writer, posted, 1, internal=False, message_type="comment")
        self.assertEqual(
            self.company.hr_config_id.hr_presence_control_email_amount,
            2,
            "fixture: one message must be under the threshold",
        )
        self.env["hr.employee"]._check_presence()
        self.assertFalse(writer.hr_presence_email_date)

    def test_an_internal_log_note_is_not_an_email(self):
        noter = self._make_employee("noter")
        posted = self._post_emails(noter, 5, internal=True)
        self._assert_authored(noter, posted, 5, internal=True, message_type="comment")
        self.env["hr.employee"]._check_presence()
        self.assertFalse(noter.hr_presence_email_date)
        self.assertEqual(noter.hr_presence_state, "absent")

    def test_a_threshold_of_zero_is_met_by_writing_nothing(self):
        self.company.hr_config_id.hr_presence_control_email_amount = 0
        silent = self._make_employee("silent")
        self.env["hr.employee"]._check_presence()
        self.assertEqual(silent.hr_presence_email_date, self._today_for(silent))
        self.assertEqual(silent.hr_presence_state, "present")

    def test_a_system_notification_is_not_an_email(self):
        notified = self._make_employee("notified")
        posted = self._post_emails(notified, 5, message_type="notification")
        self._assert_authored(
            notified, posted, 5, internal=False, message_type="notification"
        )
        self.env["hr.employee"]._check_presence()
        self.assertFalse(notified.hr_presence_email_date)


@tagged("post_install", "-at_install")
class TestDayBoundary(HrPresenceCase):
    def test_the_day_is_the_employees_own_day_not_utc(self):
        company = self.env["res.company"].create({"name": "Mexico Co"})
        calendar = self._make_calendar(company, "America/Mexico_City")
        company.write(
            {
                "resource_calendar_id": calendar.id,
                "hr_presence_control_email": True,
                "hr_presence_control_email_amount": 1,
            }
        )
        employee = self._make_employee(
            "mexican", company=company, calendar=calendar, tz="America/Mexico_City"
        )
        local_today = self._today_for(employee)
        utc_today = fields.Datetime.now().date()
        start = self.env["hr.employee"]._hr_presence_day_bounds_utc(
            "America/Mexico_City", local_today
        )[0]
        self.assertEqual(
            start,
            self._utc_bounds("America/Mexico_City", local_today),
            "the window must open at local midnight, expressed in UTC",
        )
        if local_today == utc_today:
            self.assertNotEqual(
                start,
                fields.Datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ),
                "local midnight is not UTC midnight for a UTC-6 company",
            )


@tagged("post_install", "-at_install")
class TestComputeDeclaresWhatItReads(HrPresenceCase):

    REQUIRED = frozenset(
        {
            "active",
            "company_id.hr_config_id.hr_presence_control_email",
            "company_id.hr_config_id.hr_presence_control_ip",
            "hr_presence_email_date",
            "hr_presence_ip_date",
            "hr_presence_manual_date",
            "hr_presence_manual_state",
            "is_absent",
            "resource_calendar_id",
            "resource_calendar_id.schedule_type",
            "tz",
        }
    )

    def _declared(self, field_name):
        field = self.env["hr.employee"]._fields[field_name]
        return set(self.env.registry.field_depends[field])

    def _declared_by_this_module(self):
        from odoo.addons.hr_presence.models.hr_employee import HrEmployee

        return set(HrEmployee._compute_hr_presence_state._depends)

    def test_this_modules_own_override_declares_them_and_not_by_luck(self):
        missing = self.REQUIRED - self._declared_by_this_module()
        self.assertFalse(
            missing,
            f"hr_presence's own _compute_hr_presence_state does not declare: "
            f"{sorted(missing)}",
        )

    def test_the_two_paths_a_parent_also_declares_are_deliberate(self):
        ours = self._declared_by_this_module()
        for path in ("active", "is_absent"):
            with self.subTest(path=path):
                self.assertIn(path, ours)

    def test_the_presence_state_declares_every_field_its_rule_reads(self):
        declared = self._declared("hr_presence_state")
        missing = self.REQUIRED - declared
        self.assertFalse(
            missing,
            f"_compute_hr_presence_state reads these and does not declare them: "
            f"{sorted(missing)}",
        )

    def test_the_stored_mirror_is_what_makes_the_state_searchable(self):
        employee = self.env["hr.employee"]
        self.assertFalse(employee._fields["hr_presence_state"].store)
        self.assertTrue(employee._fields["hr_presence_state_display"].store)

    def test_each_evidence_field_is_declared_by_name(self):
        declared = self._declared("hr_presence_state")
        for path in sorted(self.REQUIRED):
            with self.subTest(path=path):
                self.assertIn(path, declared)


@tagged("post_install", "-at_install")
class TestAbstainsWhereItHasNoInstrument(HrPresenceCase):

    def _employee_without_a_login(self, name, company=None, calendar=None):
        company = company or self.company
        return self.env["hr.employee"].create(
            {
                "name": name,
                "company_id": company.id,
                "resource_calendar_id": (calendar or self.calendar).id,
                "tz": "UTC",
            }
        )

    def _verdict_with(self, employee, observed):
        today = self._today_for(employee)
        working_now = frozenset(employee._get_employee_ids_working_now())
        return employee._hr_presence_verdict(today, working_now, observed)

    def test_neither_instrument_can_reach_an_employee_with_no_login(self):
        employee = self._employee_without_a_login("shop_floor")
        self.assertFalse(employee.user_id, "fixture: no login")
        self.assertIn(
            employee.id,
            employee._get_employee_ids_working_now(),
            "fixture: inside working hours, so absence is what would be inferred",
        )
        self.env["hr.employee"]._check_presence()
        self.assertFalse(
            employee.hr_presence_email_date,
            "the sweep cannot count messages without a partner",
        )
        self.assertFalse(
            employee.hr_presence_ip_date,
            "the websocket cannot find them, it searches by user_id",
        )

    def test_this_module_abstains_rather_than_inferring(self):
        employee = self._employee_without_a_login("abstained")
        self.assertEqual(
            self._verdict_with(employee, "out_of_working_hour"),
            "out_of_working_hour",
            "whatever the chain concluded is left standing",
        )
        self.assertEqual(self._verdict_with(employee, "absent"), "absent")

    def test_a_colleague_with_a_login_is_still_judged(self):
        employee = self._make_employee("has_login")
        self.assertTrue(employee.user_id)
        self.assertEqual(self._verdict_with(employee, "out_of_working_hour"), "absent")

    def test_a_manager_can_still_decide_for_them(self):
        employee = self._employee_without_a_login("overridden_anyway")
        employee.with_user(self.manager).action_set_present()
        self.assertEqual(employee.hr_presence_state, "present")
        employee.with_user(self.manager).action_set_absent()
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_an_observation_still_reaches_them(self):
        employee = self._employee_without_a_login("observed_anyway")
        self.assertEqual(self._verdict_with(employee, "present"), "present")


@tagged("post_install", "-at_install")
class TestObservationOutranksInference(HrPresenceCase):

    def _verdict_with(self, employee, observed):
        today = self._today_for(employee)
        working_now = frozenset(employee._get_employee_ids_working_now())
        return employee._hr_presence_verdict(today, working_now, observed)

    def test_the_precedence_ladder_holds_rung_by_rung(self):
        employee = self._make_employee("ladder")
        today = self._today_for(employee)
        at_work = frozenset([employee.id])
        verdict = employee._hr_presence_verdict

        employee.write(
            {"hr_presence_manual_state": "absent", "hr_presence_manual_date": today}
        )
        employee.hr_presence_ip_date = today
        self.assertEqual(verdict(today, at_work, "present"), "absent")

        employee.hr_presence_manual_state = False
        self.assertEqual(verdict(today, at_work, "absent"), "present")

        employee.hr_presence_ip_date = False
        self.assertEqual(verdict(today, at_work, "present"), "present")

        self.assertEqual(verdict(today, frozenset(), "absent"), "out_of_working_hour")

        self.assertEqual(verdict(today, at_work, "absent"), "absent")

    def test_the_abstention_rung_sits_below_the_observation_and_above_the_inference(
        self,
    ):
        with_login = self._make_employee("laddered_user")
        today = self._today_for(with_login)
        without = self.env["hr.employee"].create(
            {
                "name": "laddered_nouser",
                "company_id": self.company.id,
                "resource_calendar_id": self.calendar.id,
                "tz": "UTC",
            }
        )
        at_work = frozenset([with_login.id, without.id])
        self.assertEqual(
            with_login._hr_presence_verdict(today, at_work, "out_of_working_hour"),
            "absent",
            "rung 7 for the colleague this module can measure",
        )
        self.assertEqual(
            without._hr_presence_verdict(today, at_work, "out_of_working_hour"),
            "out_of_working_hour",
            "rung 4 for the employee it cannot",
        )
        self.assertEqual(
            without._hr_presence_verdict(today, at_work, "present"),
            "present",
            "and rung 3 still sits above rung 4",
        )

    def test_an_observation_below_survives_this_modules_inference(self):
        employee = self._make_employee("observed")
        self.assertEqual(
            self._verdict_with(employee, "out_of_working_hour"),
            "absent",
            "fixture: with nothing observed this employee is absentable, so the "
            "next assertion tests the observation and not the schedule",
        )
        self.assertEqual(self._verdict_with(employee, "present"), "present")

    def test_an_observation_does_not_survive_a_managers_override(self):
        employee = self._make_employee("overruled")
        employee.with_user(self.manager).action_set_absent()
        self.assertEqual(self._verdict_with(employee, "present"), "absent")

    def test_this_modules_own_evidence_still_reads_present(self):
        employee = self._make_employee("evidenced")
        employee.hr_presence_ip_date = self._today_for(employee)
        self.assertEqual(self._verdict_with(employee, "absent"), "present")

    def test_an_observation_outranks_the_time_off_excuse_too(self):
        employee = self._make_employee("working_anyway")
        self._approve_leave(employee)
        employee.invalidate_recordset()
        self.assertTrue(employee.is_absent)
        self.assertEqual(
            self._verdict_with(employee, "out_of_working_hour"),
            "out_of_working_hour",
            "fixture: the leave alone excuses them",
        )
        self.assertEqual(self._verdict_with(employee, "present"), "present")

    def test_nothing_observed_still_flags_the_truant(self):
        employee = self._make_employee("still_truant")
        for observed in ("out_of_working_hour", "absent", "archive", False, None):
            with self.subTest(observed=observed):
                self.assertEqual(self._verdict_with(employee, observed), "absent")


@tagged("post_install", "-at_install")
class TestDayWindowsTile(HrPresenceCase):

    ZONES = (
        "UTC",
        "America/Mexico_City",
        "America/Santiago",
        "Asia/Beirut",
        "Australia/Lord_Howe",
        "Asia/Kathmandu",
        "Pacific/Chatham",
        "Pacific/Kiritimati",
    )

    def _bounds(self, tz_name, day):
        return self.env["hr.employee"]._hr_presence_day_bounds_utc(tz_name, day)

    def test_the_two_days_that_used_to_leave_an_hour_uncovered(self):
        for tz_name, day in (
            ("America/Santiago", date(2026, 4, 4)),
            ("Asia/Beirut", date(2026, 10, 24)),
        ):
            with self.subTest(tz=tz_name, day=day):
                _start, end = self._bounds(tz_name, day)
                next_start, _ = self._bounds(tz_name, day + timedelta(days=1))
                self.assertEqual(
                    end,
                    next_start,
                    "the hour between these two windows belonged to nobody",
                )

    def test_every_day_of_a_year_tiles_in_every_zone(self):
        for tz_name in self.ZONES:
            day = date(2026, 1, 1)
            previous_end = None
            while day <= date(2026, 12, 31):
                start, end = self._bounds(tz_name, day)
                self.assertLess(start, end, f"{tz_name} {day}: inverted window")
                if previous_end is not None:
                    self.assertEqual(
                        start,
                        previous_end,
                        f"{tz_name} {day}: window does not meet the previous day",
                    )
                previous_end = end
                day += timedelta(days=1)

    def test_a_window_is_a_local_day_long_except_across_a_dst_step(self):
        start, end = self._bounds("America/Mexico_City", date(2026, 6, 15))
        self.assertEqual(end - start, timedelta(hours=24))
        short_start, short_end = self._bounds("Europe/Brussels", date(2026, 3, 29))
        self.assertEqual(short_end - short_start, timedelta(hours=23))
        long_start, long_end = self._bounds("Europe/Brussels", date(2026, 10, 25))
        self.assertEqual(long_end - long_start, timedelta(hours=25))

    @freeze_time("2026-04-05 03:30:00")
    def test_a_message_in_the_formerly_uncovered_hour_still_counts(self):
        company = self.env["res.company"].create({"name": "Santiago Co"})
        calendar = self._make_calendar(company, "America/Santiago")
        company.write(
            {
                "resource_calendar_id": calendar.id,
                "hr_presence_control_email": True,
                "hr_presence_control_email_amount": 1,
            }
        )
        employee = self._make_employee(
            "santiago", company=company, calendar=calendar, tz="America/Santiago"
        )
        today = self._today_for(employee)
        self.assertEqual(today, date(2026, 4, 4), "fixture: the local day")

        start, end = self._bounds("America/Santiago", today)
        superseded_end = to_timezone(None)(
            datetime.combine(today, time.max).replace(
                tzinfo=timezone("America/Santiago")
            )
        )
        posted = self._post_emails(employee, 1)
        self._assert_authored(
            employee, posted, 1, internal=False, message_type="comment"
        )
        self.assertTrue(
            start <= posted.date < end,
            f"fixture: {posted.date} must be inside [{start}, {end})",
        )
        self.assertGreater(
            posted.date,
            superseded_end,
            "fixture: the message must fall AFTER the end the old shape computed, "
            "or this test does not reach the hour that used to be dropped",
        )

        self.env["hr.employee"]._check_presence()
        self.assertEqual(employee.hr_presence_email_date, today)


@tagged("post_install", "-at_install")
class TestTheMirrorIsRightFromBirth(HrPresenceCase):

    def test_a_new_employee_is_mirrored_at_once(self):
        employee = self._make_employee("newborn")
        self.assertEqual(
            employee.hr_presence_state,
            "absent",
            "fixture: the live state must differ from the field default, or this "
            "test would pass against a mirror that was never written",
        )
        self.assertEqual(employee.hr_presence_state_display, employee.hr_presence_state)

    def test_a_new_employee_is_findable_by_the_filter_at_once(self):
        employee = self._make_employee("findable")
        self.assertIn(
            employee,
            self.env["hr.employee"].search(
                [("hr_presence_state_display", "=", "absent")]
            ),
        )

    def test_a_company_that_does_not_use_the_feature_is_left_alone(self):
        plain = self.env["res.company"].create({"name": "Unmirrored Co"})
        calendar = self._make_calendar(plain, "UTC")
        plain.resource_calendar_id = calendar
        employee = self._make_employee("unmirrored", company=plain, calendar=calendar)
        self.assertEqual(employee.hr_presence_state_display, "out_of_working_hour")

    def test_a_batch_is_mirrored_in_one_pass(self):
        users = [self._make_user(f"u_batch{index}", self.company) for index in range(8)]
        cursor_class = type(self.env.cr)
        execute = cursor_class.execute
        mirror_statements = []

        def recording(cursor, query, *args, **kwargs):
            if "hr_presence_state_display" in str(query):
                mirror_statements.append(str(query))
            return execute(cursor, query, *args, **kwargs)

        with patch.object(cursor_class, "execute", recording):
            employees = self.env["hr.employee"].create(
                [
                    {
                        "name": f"batch{index}",
                        "company_id": self.company.id,
                        "user_id": user.id,
                        "resource_calendar_id": self.calendar.id,
                        "tz": "UTC",
                    }
                    for index, user in enumerate(users)
                ]
            )
            self.env.flush_all()
        self.assertEqual(
            set(employees.mapped("hr_presence_state")),
            {"absent"},
            "fixture: the live state must differ from the field default, or this "
            "test would pass against a mirror that was never written",
        )
        self.assertEqual(
            set(employees.mapped("hr_presence_state_display")),
            {"absent"},
            "every employee of the batch, not just the first",
        )
        self.assertLess(
            len(mirror_statements),
            len(employees),
            "the refresh must not be per-record",
        )

    def test_the_mirror_is_a_plain_field_not_a_stored_compute(self):
        field = self.env["hr.employee"]._fields["hr_presence_state_display"]
        self.assertTrue(field.store)
        self.assertFalse(field.compute)
        self.assertIn(
            "user_id.im_status",
            self.env.registry.field_depends[
                self.env["hr.employee"]._fields["hr_presence_state"]
            ],
            "fixture: the high-churn dependency that makes a stored compute wrong",
        )


@tagged("post_install", "-at_install")
class TestSweep(HrPresenceCase):
    def test_the_sweep_mirrors_the_state_into_the_searchable_field(self):
        truant = self._make_employee("mirrored")
        self.env["hr.employee"]._check_presence()
        self.assertEqual(truant.hr_presence_state_display, "absent")
        self.assertEqual(
            self.env["hr.employee"].search(
                [("hr_presence_state_display", "=", "absent"), ("id", "=", truant.id)]
            ),
            truant,
        )

    def test_the_mirror_carries_every_state_including_archive(self):
        gone = self._make_employee("archived_mirror")
        gone.action_archive()
        self.env["hr.employee"]._check_presence()
        self.assertEqual(gone.hr_presence_state_display, "archive")

    def test_the_sweep_leaves_an_uncontrolled_company_alone(self):
        plain = self.env["res.company"].create({"name": "Untouched Co"})
        calendar = self._make_calendar(plain, "UTC")
        plain.resource_calendar_id = calendar
        employee = self._make_employee("untouched", company=plain, calendar=calendar)
        employee.hr_presence_state_display = "present"
        self.env["hr.employee"]._check_presence()
        self.assertEqual(employee.hr_presence_state_display, "present")

    def test_no_company_keeps_a_write_only_compute_stamp(self):
        self.assertNotIn(
            "hr_presence_last_compute_date", self.env["res.company"]._fields
        )


@tagged("post_install", "-at_install")
class TestTheCronEntryPoint(HrPresenceCase):

    def test_the_cron_record_still_points_at_a_method_that_exists(self):
        cron = self.env.ref("hr_presence.ir_cron_presence_control")
        self.assertEqual(cron.model_id.model, "hr.employee")
        self.assertEqual(cron.state, "code")
        self.assertEqual(cron.code.strip(), "model._check_presence()")
        self.assertTrue(
            hasattr(self.env[cron.model_id.model], "_check_presence"),
            "the cron names a method the model does not have",
        )

    def test_running_the_cron_as_it_is_scheduled_sweeps(self):
        company = self.env["res.company"].create({"name": "Cron Co"})
        calendar = self._make_calendar(company, "UTC")
        company.write(
            {"resource_calendar_id": calendar.id, "hr_presence_control_ip": True}
        )
        employee = self._make_employee("cronned", company=company, calendar=calendar)
        employee.hr_presence_state_display = "present"

        cron = self.env.ref("hr_presence.ir_cron_presence_control")
        self.assertNotEqual(
            company,
            cron.user_id.company_id,
            "fixture: the company under test must not be the cron user's own, "
            "or this test cannot tell a company-wide sweep from self.env.company "
            "(which resolves to exactly that company)",
        )
        cron.sudo().with_user(cron.user_id).ir_actions_server_id.run()
        self.assertEqual(
            employee.hr_presence_state_display,
            "absent",
            "the cron must sweep every controlled company",
        )


@tagged("post_install", "-at_install")
class TestSettingsTriggerTheSweep(HrPresenceCase):

    def _save_settings(self, company, **values):
        settings = (
            self.env["res.config.settings"]
            .with_company(company)
            .create({"company_id": company.id, **values})
        )
        settings.set_values()
        return settings

    def test_turning_a_control_on_sweeps_at_once(self):
        company = self.env["res.company"].create({"name": "Settings Co"})
        calendar = self._make_calendar(company, "UTC")
        company.resource_calendar_id = calendar
        employee = self._make_employee("swept", company=company, calendar=calendar)
        self.assertEqual(
            employee.hr_presence_state_display,
            "out_of_working_hour",
            "fixture: the stored mirror starts at its default",
        )
        self._save_settings(company, hr_presence_control_ip=True)
        self.assertTrue(company.hr_config_id.hr_presence_control_ip)
        self.assertEqual(
            employee.hr_presence_state_display,
            "absent",
            "the sweep must have run as part of saving the setting",
        )

    def test_saving_settings_that_change_nothing_does_not_sweep(self):
        company = self.env["res.company"].create({"name": "Idle Settings Co"})
        calendar = self._make_calendar(company, "UTC")
        company.write(
            {"resource_calendar_id": calendar.id, "hr_presence_control_ip": True}
        )
        employee = self._make_employee("untouched", company=company, calendar=calendar)
        self.env["hr.employee"]._check_presence()
        self.assertEqual(employee.hr_presence_state_display, "absent")
        employee.hr_presence_state_display = "present"
        self._save_settings(company, hr_presence_control_ip=True)
        self.assertEqual(
            employee.hr_presence_state_display,
            "present",
            "re-saving an unchanged setting must not re-sweep",
        )

    def test_turning_every_control_off_does_not_sweep(self):
        company = self.env["res.company"].create({"name": "Off Settings Co"})
        calendar = self._make_calendar(company, "UTC")
        company.write(
            {"resource_calendar_id": calendar.id, "hr_presence_control_ip": True}
        )
        employee = self._make_employee("switching", company=company, calendar=calendar)
        employee.hr_presence_state_display = "present"
        self._save_settings(company, hr_presence_control_ip=False)
        self.assertFalse(company.hr_config_id.hr_presence_control_ip)
        self.assertEqual(employee.hr_presence_state_display, "present")


@tagged("post_install", "-at_install")
class TestOneUserTwoEmployees(HrPresenceCase):

    def test_each_employee_is_judged_against_its_own_company_threshold(self):
        lenient = self.env["res.company"].create({"name": "Lenient Co"})
        strict = self.env["res.company"].create({"name": "Strict Co"})
        lenient_cal = self._make_calendar(lenient, "UTC")
        strict_cal = self._make_calendar(strict, "UTC")
        lenient.write(
            {
                "resource_calendar_id": lenient_cal.id,
                "hr_presence_control_email": True,
                "hr_presence_control_email_amount": 1,
            }
        )
        strict.write(
            {
                "resource_calendar_id": strict_cal.id,
                "hr_presence_control_email": True,
                "hr_presence_control_email_amount": 99,
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "shared",
                "login": "shared_user",
                "company_id": lenient.id,
                "company_ids": [(6, 0, [lenient.id, strict.id])],
            }
        )
        here = self._make_employee(
            "lenient_emp", company=lenient, calendar=lenient_cal, user=user
        )
        there = self._make_employee(
            "strict_emp", company=strict, calendar=strict_cal, user=user
        )
        self.assertEqual(
            here.user_id.partner_id,
            there.user_id.partner_id,
            "fixture: both employees must share one partner, or the two "
            "thresholds are never applied to the same messages",
        )
        posted = self._post_emails(here, 2)
        self._assert_authored(here, posted, 2, internal=False, message_type="comment")

        self.env["hr.employee"]._check_presence()
        self.assertEqual(
            here.hr_presence_email_date,
            self._today_for(here),
            "the company asking for one email is satisfied",
        )
        self.assertFalse(
            there.hr_presence_email_date,
            "the company asking for 99 is not, from the same messages",
        )

    @freeze_time("2026-04-05 03:30:00")
    def test_two_employees_of_one_user_keep_their_own_timezone(self):
        first_company = self.env["res.company"].create({"name": "TZ One Co"})
        second_company = self.env["res.company"].create({"name": "TZ Two Co"})
        first_cal = self._make_calendar(first_company, "UTC")
        second_cal = self._make_calendar(second_company, "Pacific/Midway")
        first_company.resource_calendar_id = first_cal
        second_company.resource_calendar_id = second_cal
        user = self.env["res.users"].create(
            {
                "name": "one",
                "login": "one_user",
                "company_id": first_company.id,
                "company_ids": [(6, 0, [first_company.id, second_company.id])],
            }
        )
        first = self._make_employee(
            "first", company=first_company, calendar=first_cal, user=user
        )
        second = self._make_employee(
            "second",
            company=second_company,
            calendar=second_cal,
            tz="Pacific/Midway",
            user=user,
        )
        second.invalidate_recordset()
        self.assertEqual(
            first.user_id.partner_id,
            second.user_id.partner_id,
            "fixture: one partner behind both",
        )
        self.assertEqual((first.tz, second.tz), ("UTC", "Pacific/Midway"))
        today = (first | second)._hr_presence_today()
        self.assertEqual(today[first.id], date(2026, 4, 5))
        self.assertEqual(today[second.id], date(2026, 4, 4))


@tagged("post_install", "-at_install")
class TestActions(HrPresenceCase):
    def test_the_sms_action_reaches_the_template_this_module_ships(self):
        template = self.env.ref("hr_presence.sms_template_presence")
        self.assertEqual(template.model_id.model, "hr.employee")
        employee = self._make_employee("texted")
        action = employee.with_user(self.manager).action_send_sms()
        self.assertEqual(action["context"]["default_template_id"], template.id)
        self.assertNotIn("default_body", action["context"])

    def test_the_email_action_reaches_the_template_this_module_ships(self):
        template = self.env.ref("hr_presence.mail_template_presence")
        employee = self._make_employee("mailed")
        action = employee.with_user(self.manager).action_send_email()
        self.assertEqual(action["res_model"], "wizard.mail.message.send")
        self.assertEqual(action["context"]["default_template_id"], template.id)
        self.assertEqual(action["context"]["default_res_ids"], employee.ids)

    def test_the_log_note_names_the_state_in_words(self):
        employee = self._make_employee("logged")
        self.env["hr.employee"]._check_presence()
        employee.with_user(self.manager).action_send_log()
        body = employee.message_ids[:1].body
        self.assertIn("Absent", body)
        self.assertNotIn("out_of_working_hour", body)

    def test_the_time_off_action_targets_one_employee_or_many(self):
        one = self._make_employee("solo")
        two = self._make_employee("duo")
        self.assertEqual(one.action_view_leave_request()["res_model"], "hr.leave")
        self.assertEqual(
            (one | two).action_view_leave_request()["res_model"],
            "wizard.hr.leave.create",
        )


@tagged("post_install", "-at_install")
class TestTheWebsocketRecordsTheEvidence(HrPresenceCase):

    def _presence(self, employee, remote_addr):
        from odoo.addons.mail.models.ir_websocket import IrWebsocket as MailWebsocket

        class FakeRequest:
            class httprequest:
                pass

        FakeRequest.httprequest.remote_addr = remote_addr
        websocket = self.env["ir.websocket"].with_user(employee.user_id)
        with (
            patch.object(
                MailWebsocket,
                "_update_mail_presence",
                lambda self, inactivity_period: None,
            ),
            patch("odoo.addons.hr_presence.models.ir_websocket.wsrequest", FakeRequest),
        ):
            websocket._update_mail_presence(0)
        employee.invalidate_recordset()

    def test_a_connection_from_a_listed_address_is_recorded(self):
        employee = self._make_employee("connector")
        self.assertFalse(employee.hr_presence_ip_date, "fixture: nothing recorded yet")
        self._presence(employee, "10.0.0.1")
        self.assertEqual(employee.hr_presence_ip_date, self._today_for(employee))
        self.assertEqual(employee.hr_presence_state, "present")

    def test_a_connection_from_an_unlisted_address_records_nothing(self):
        employee = self._make_employee("stranger")
        self.assertIn(
            "10.0.0.1",
            self.company._hr_presence_valid_ips(),
            "fixture: the company must have a list, or nothing could be rejected",
        )
        self._presence(employee, "192.168.55.55")
        self.assertFalse(employee.hr_presence_ip_date)
        self.assertEqual(employee.hr_presence_state, "absent")

    def test_a_company_that_does_not_use_ip_control_records_nothing(self):
        plain = self.env["res.company"].create({"name": "No IP Co"})
        calendar = self._make_calendar(plain, "UTC")
        plain.write(
            {
                "resource_calendar_id": calendar.id,
                "hr_presence_control_email": True,
                "hr_presence_control_ip": False,
            }
        )
        employee = self._make_employee("unwatched", company=plain, calendar=calendar)
        self._presence(employee, "10.0.0.1")
        self.assertFalse(employee.hr_presence_ip_date)

    def test_the_stored_mirror_follows_the_connection_at_once(self):
        employee = self._make_employee("filtered")
        self.env["hr.employee"]._check_presence()
        self.assertEqual(employee.hr_presence_state_display, "absent")
        self._presence(employee, "10.0.0.1")
        self.assertEqual(employee.hr_presence_state_display, "present")
        self.assertIn(
            employee,
            self.env["hr.employee"].search(
                [("hr_presence_state_display", "=", "present")]
            ),
        )

    def test_a_second_heartbeat_the_same_day_writes_nothing_more(self):
        employee = self._make_employee("repeater")
        self._presence(employee, "10.0.0.1")
        stamped = employee.write_date
        self._presence(employee, "10.0.0.1")
        self.assertEqual(
            employee.write_date, stamped, "the date guard must short-circuit"
        )

    def test_a_stamp_lost_to_a_rollback_is_recorded_again(self):
        employee = self._make_employee("retried")
        self._presence(employee, "10.0.0.1")
        self.assertTrue(employee.hr_presence_ip_date)
        employee.hr_presence_ip_date = False
        self._presence(employee, "10.0.0.1")
        self.assertEqual(employee.hr_presence_ip_date, self._today_for(employee))


@tagged("post_install", "-at_install")
class TestWebsocketGate(HrPresenceCase):

    def test_the_gate_follows_the_setting(self):
        Company = self.env["res.company"]
        self.assertTrue(Company._is_presence_ip_tracking_enabled())
        self.env["res.company"].search([]).hr_config_id.hr_presence_control_ip = False
        self.assertFalse(
            Company._is_presence_ip_tracking_enabled(),
            "the ormcache must be invalidated by the field it answers about",
        )
        self.company.hr_config_id.hr_presence_control_ip = True
        self.assertTrue(Company._is_presence_ip_tracking_enabled())

    def test_the_valid_ip_list_tolerates_the_spacing_people_type(self):
        self.company.hr_config_id.hr_presence_control_ip_list = (
            " 10.0.0.1 ,10.0.0.2 ,, "
        )
        self.assertEqual(
            self.company._hr_presence_valid_ips(), {"10.0.0.1", "10.0.0.2"}
        )
        self.company.hr_config_id.hr_presence_control_ip_list = False
        self.assertEqual(self.company._hr_presence_valid_ips(), set())


@tagged("post_install", "-at_install")
class TestGearMenuBindings(HrPresenceCase):

    def _presence_actions(self):
        return self.env["ir.actions.server"].search(
            [
                ("binding_model_id.model", "=", "hr.employee"),
                ("hr_presence_section", "!=", False),
            ]
        )

    def test_every_presence_action_declares_its_section(self):
        sections = {
            action.name: action.hr_presence_section
            for action in self._presence_actions()
        }
        self.assertEqual(
            sections,
            {
                "Set Present": "state",
                "Set Absent": "state",
                "Add a Log Note": "follow_up",
                "Send Email\u2026": "follow_up",
                "Send SMS\u2026": "follow_up",
                "Create a Time Off": "follow_up",
            },
        )

    def test_no_other_action_bound_to_the_employee_claims_a_section(self):
        bound = self.env["ir.actions.server"].search(
            [("binding_model_id.model", "=", "hr.employee")]
        )
        foreign = bound - self._presence_actions()
        self.assertTrue(foreign, "fixture: some other module binds to hr.employee")
        self.assertFalse(foreign.filtered("hr_presence_section"))

    def test_the_section_travels_with_the_binding(self):
        bindings = self.env["ir.actions.actions"]._get_bindings("hr.employee")
        by_name = {a["name"]: a for a in bindings["action"]}
        self.assertEqual(by_name["Set Present"]["hr_presence_section"], "state")
        self.assertEqual(by_name["Send SMS\u2026"]["hr_presence_section"], "follow_up")
        self.assertFalse(by_name["Create User"].get("hr_presence_section"))

    def test_the_sections_order_the_submenu(self):
        actions = self._presence_actions().sorted(
            lambda a: (a.hr_presence_section != "state", a.binding_sequence)
        )
        self.assertEqual(
            actions.mapped("name"),
            [
                "Set Present",
                "Set Absent",
                "Add a Log Note",
                "Send Email\u2026",
                "Send SMS\u2026",
                "Create a Time Off",
            ],
        )


@tagged("post_install", "-at_install")
class TestUsersLogIsNoLongerUsed(HrPresenceCase):
    def test_this_module_adds_no_field_to_res_users_log(self):
        self.assertNotIn("ip", self.env["res.users.log"]._fields)

    def test_the_login_date_survives_the_vacuum(self):
        employee = self._make_employee("logger")
        user = employee.user_id
        self.env["res.users.log"].sudo().search([("create_uid", "=", user.id)]).unlink()
        self.env["res.users.log"].with_user(user).sudo().create({})
        user.invalidate_recordset(["login_date", "log_ids"])
        login_date = user.login_date
        self.assertTrue(login_date)
        employee.hr_presence_ip_date = self._today_for(employee)
        self.env["res.users.log"].sudo()._gc_user_logs()
        user.invalidate_recordset(["login_date", "log_ids"])
        self.assertEqual(user.login_date, login_date)
        self.assertEqual(
            employee.hr_presence_ip_date,
            self._today_for(employee),
            "the vacuum cannot reach the presence evidence any more",
        )
