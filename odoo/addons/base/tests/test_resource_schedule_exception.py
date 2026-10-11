from datetime import UTC, datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from .common import ResourceCase


@tagged("post_install", "-at_install")
class TestLeaveCompanyFallback(TransactionCase):
    def test_leave_company_follows_resource(self):
        company_b = self.env["res.company"].create({"name": "Company B"})
        resource_b = self.env["resource.resource"].create(
            {
                "name": "B worker",
                "company_id": company_b.id,
                "calendar_id": False,
                "tz": "UTC",
            }
        )
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "B leave",
                "resource_id": resource_b.id,
                "date_from": datetime(2025, 1, 6, 0, 0),
                "date_to": datetime(2025, 1, 6, 23, 59),
            }
        )
        self.assertEqual(leave.calendar_id, resource_b.calendar_id)
        self.assertEqual(
            leave.company_id,
            company_b,
            "the resource's company must beat the acting company",
        )


class TestLeaveSecurityRule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(cls.env, login="resource_employee")
        cls.machine = cls.env["resource.resource"].create(
            {
                "name": "CNC machine",
                "type": "material",
                "calendar_id": cls.env.ref("base.resource_calendar_std").id,
                "tz": "UTC",
            }
        )
        cls.machine_leave = cls.env["resource.schedule.exception"].create(
            {
                "name": "Maintenance",
                "resource_id": cls.machine.id,
                "date_from": datetime(2025, 7, 1),
                "date_to": datetime(2025, 7, 2),
            }
        )

    def test_employee_cannot_write_machine_downtime(self):
        with self.assertRaises(AccessError):
            self.machine_leave.with_user(self.employee).write({"name": "hijacked"})

    def test_employee_cannot_unlink_machine_downtime(self):
        with self.assertRaises(AccessError):
            self.machine_leave.with_user(self.employee).unlink()

    def test_employee_cannot_create_machine_downtime(self):
        with self.assertRaises(AccessError):
            self.env["resource.schedule.exception"].with_user(self.employee).create(
                {
                    "name": "Fabricated outage",
                    "resource_id": self.machine.id,
                    "date_from": datetime(2025, 8, 1),
                    "date_to": datetime(2025, 8, 30),
                }
            )

    def test_employee_can_still_read_machine_downtime(self):
        self.machine_leave.with_user(self.employee).read(["name"])

    def test_employee_manages_own_time_off(self):
        own_resource = self.env["resource.resource"].create(
            {
                "name": "Employee resource",
                "user_id": self.employee.id,
                "calendar_id": self.env.ref("base.resource_calendar_std").id,
                "tz": "UTC",
            }
        )
        leave = (
            self.env["resource.schedule.exception"]
            .with_user(self.employee)
            .create(
                {
                    "name": "My day off",
                    "resource_id": own_resource.id,
                    "date_from": datetime(2025, 7, 10),
                    "date_to": datetime(2025, 7, 10, 23, 59),
                }
            )
        )
        leave.write({"name": "My renamed day off"})
        leave.unlink()

    def test_manager_still_manages_machine_downtime(self):
        manager = new_test_user(
            self.env, login="resource_manager", groups="base.group_erp_manager"
        )
        self.machine_leave.with_user(manager).write({"name": "Rescheduled maintenance"})
        self.assertEqual(self.machine_leave.name, "Rescheduled maintenance")


@tagged("post_install", "-at_install")
class TestDeletingAScheduleDoesNotCreateAGlobalHoliday(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Calendar = cls.env["resource.calendar"]
        cls.Resource = cls.env["resource.resource"]
        cls.Leave = cls.env["resource.schedule.exception"]
        cls.start = datetime(2026, 6, 1, tzinfo=UTC)
        cls.stop = datetime(2026, 6, 6, tzinfo=UTC)

    def _bystander(self):
        return self.Calendar.create({"name": "Bystander schedule"})

    def test_deleting_a_schedule_does_not_widen_its_time_off(self):
        bystander = self._bystander()
        doomed = self.Calendar.create({"name": "Doomed schedule"})
        self.Leave.create(
            {
                "name": "Doomed team offsite",
                "calendar_id": doomed.id,
                "date_from": datetime(2026, 6, 3, 0, 0),
                "date_to": datetime(2026, 6, 3, 23, 59),
            }
        )
        self.env.flush_all()
        before = bystander.get_work_hours_count(self.start, self.stop)

        doomed.attendance_ids.unlink()
        doomed.unlink()
        self.env.flush_all()
        bystander.invalidate_recordset()

        self.assertEqual(
            bystander.get_work_hours_count(self.start, self.stop),
            before,
            "an unrelated schedule lost a day because a deleted schedule's time off"
            " kept a NULL calendar_id, which _leave_intervals_batch reads as"
            " 'applies to every calendar'",
        )

    def test_deleting_a_calendarless_resource_does_not_widen_its_time_off(self):
        bystander = self._bystander()
        machine = self.Resource.create(
            {
                "name": "Lathe #3",
                "type": "material",
                "calendar_id": False,
                "tz": "UTC",
            }
        )
        self.env.flush_all()
        self.Leave.create(
            {
                "name": "Lathe maintenance",
                "resource_id": machine.id,
                "date_from": datetime(2026, 6, 4, 0, 0),
                "date_to": datetime(2026, 6, 4, 23, 59),
            }
        )
        self.env.flush_all()
        before = bystander.get_work_hours_count(self.start, self.stop)

        machine.unlink()
        self.env.flush_all()
        bystander.invalidate_recordset()

        self.assertEqual(
            bystander.get_work_hours_count(self.start, self.stop),
            before,
            "an unrelated schedule lost a day because a deleted resource's personal"
            " time off kept a NULL resource_id AND a NULL calendar_id, which"
            " _leave_intervals_batch reads as 'applies to everything'",
        )

    def test_deleting_a_resource_that_has_a_calendar_is_already_safe(self):
        bystander = self._bystander()
        own = self.Calendar.create({"name": "Machine shift"})
        self.env.flush_all()
        machine = self.Resource.create(
            {
                "name": "Press #1",
                "type": "material",
                "calendar_id": own.id,
                "tz": "UTC",
            }
        )
        self.env.flush_all()
        self.Leave.create(
            {
                "name": "Press maintenance",
                "resource_id": machine.id,
                "date_from": datetime(2026, 6, 4, 0, 0),
                "date_to": datetime(2026, 6, 4, 23, 59),
            }
        )
        self.env.flush_all()
        before = bystander.get_work_hours_count(self.start, self.stop)
        machine.unlink()
        self.env.flush_all()
        bystander.invalidate_recordset()
        self.assertEqual(bystander.get_work_hours_count(self.start, self.stop), before)

    def test_a_genuinely_global_leave_still_applies_everywhere(self):
        bystander = self._bystander()
        before = bystander.get_work_hours_count(self.start, self.stop)
        self.Leave.create(
            {
                "name": "Public holiday",
                "calendar_id": False,
                "date_from": datetime(2026, 6, 3, 0, 0),
                "date_to": datetime(2026, 6, 3, 23, 59),
            }
        )
        self.env.flush_all()
        bystander.invalidate_recordset()
        self.assertLess(
            bystander.get_work_hours_count(self.start, self.stop),
            before,
            "a leave declared with no calendar is the real wildcard and must keep"
            " reaching every schedule",
        )


@tagged("post_install", "-at_install")
class TestLeaveDateToMultiCompanyTz(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "TZ Co A"})
        cls.company_b = cls.env["res.company"].create({"name": "TZ Co B"})
        cls.company_a.resource_calendar_id.tz = "Europe/Brussels"
        cls.company_b.resource_calendar_id.tz = "Asia/Tokyo"

    def _tzless_leaves_model(self):
        root = self.env.ref("base.user_root")
        root.tz = False
        return (
            self.env["resource.schedule.exception"]
            .sudo()
            .with_context(
                tz=None,
                allowed_company_ids=[self.company_a.id, self.company_b.id],
            )
        )

    def test_multi_company_batch_create_does_not_raise(self):
        leaves = self._tzless_leaves_model().create(
            [
                {
                    "name": "A",
                    "calendar_id": self.company_a.resource_calendar_id.id,
                    "date_from": datetime(2025, 1, 6, 8, 0),
                },
                {
                    "name": "B",
                    "calendar_id": self.company_b.resource_calendar_id.id,
                    "date_from": datetime(2025, 1, 6, 8, 0),
                },
            ]
        )
        self.assertEqual(len(leaves), 2)
        self.assertTrue(all(leaves.mapped("date_to")))

    def test_date_to_uses_each_leaves_own_calendar_tz(self):
        leaves = self._tzless_leaves_model().create(
            [
                {
                    "name": "A",
                    "calendar_id": self.company_a.resource_calendar_id.id,
                    "date_from": datetime(2025, 1, 6, 8, 0),
                },
                {
                    "name": "B",
                    "calendar_id": self.company_b.resource_calendar_id.id,
                    "date_from": datetime(2025, 1, 6, 8, 0),
                },
            ]
        )
        leave_a, leave_b = leaves[0], leaves[1]
        self.assertEqual(leave_a.date_to, datetime(2025, 1, 6, 23, 0))
        self.assertEqual(leave_b.date_to, datetime(2025, 1, 6, 15, 0))

    def test_date_to_calendar_tz_wins_over_the_acting_users_tz(self):
        leave = (
            self.env["resource.schedule.exception"]
            .with_context(tz="Asia/Tokyo")
            .create(
                {
                    "name": "A",
                    "calendar_id": self.company_a.resource_calendar_id.id,
                    "date_from": datetime(2025, 1, 6, 8, 0),
                }
            )
        )
        self.assertEqual(leave.date_to, datetime(2025, 1, 6, 23, 0))


@tagged("post_install", "-at_install")
class TestLeaveDefaults(TransactionCase):
    def test_default_dates_use_the_calendar_date_not_the_utc_date(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Mexico", "tz": "America/Mexico_City"}
        )
        with freeze_time("2026-09-06 04:30:00"):
            defaults = (
                self.env["resource.schedule.exception"]
                .with_context(default_calendar_id=calendar.id)
                .default_get(["date_from", "date_to", "calendar_id"])
            )
        self.assertEqual(defaults["date_from"], datetime(2026, 9, 5, 6, 0))
        self.assertEqual(defaults["date_to"], datetime(2026, 9, 6, 6, 0))


class TestExceptionCompanies(ResourceCase):
    def test_cross_company_leave_is_rejected(self):
        other_company = self.env["res.company"].create({"name": "Other SP Co"})
        other_calendar = self.env["resource.calendar"].create(
            {"name": "other", "company_id": other_company.id, "tz": "UTC"}
        )
        resource = self._resource(name="Company A resource")
        with self.assertRaises(UserError) as caught:
            leave = self.env["resource.schedule.exception"].create(
                {
                    "name": "cross company",
                    "calendar_id": other_calendar.id,
                    "resource_id": resource.id,
                    "date_from": datetime(2026, 3, 2, 8, 0),
                    "date_to": datetime(2026, 3, 2, 17, 0),
                }
            )
            leave.flush_recordset()
        self.assertIn("compan", str(caught.exception).lower())

    def test_company_less_calendar_is_valid_for_any_resource(self):
        shared = self.env["resource.calendar"].create(
            {"name": "shared", "company_id": False, "tz": "UTC"}
        )
        resource = self._resource(name="Shared cal", calendar_id=shared.id)
        resource.flush_recordset()
        self.assertEqual(resource.calendar_id, shared)

    def _global_leave(self, calendar):
        return self.env["resource.schedule.exception"].create(
            {
                "name": "Public holiday",
                "calendar_id": calendar.id,
                "date_from": datetime(2026, 3, 2, 8, 0),
                "date_to": datetime(2026, 3, 2, 17, 0),
            }
        )

    def _sees_leave(self, resource):
        return bool(
            self.calendar._leave_intervals_batch(
                datetime(2026, 3, 1).replace(tzinfo=UTC),
                datetime(2026, 3, 8).replace(tzinfo=UTC),
                resource,
            )[resource.id]
        )

    def test_company_less_resource_sees_global_leaves(self):
        shared_calendar = self.env["resource.calendar"].create(
            {"name": "shared cal", "company_id": False, "tz": "UTC"}
        )
        resource = self._resource(
            name="No company", company_id=False, calendar_id=shared_calendar.id
        )
        leave = self._global_leave(shared_calendar)
        self.env.flush_all()
        self.assertTrue(leave.company_id, "precondition: the leave names a company")
        self.assertFalse(resource.company_id)
        self.assertTrue(
            bool(
                shared_calendar._leave_intervals_batch(
                    datetime(2026, 3, 1).replace(tzinfo=UTC),
                    datetime(2026, 3, 8).replace(tzinfo=UTC),
                    resource,
                )[resource.id]
            )
        )

    def test_a_leave_cannot_be_stranded_in_another_company(self):
        other_company = self.env["res.company"].create({"name": "Stranded Co"})
        other_calendar = self.env["resource.calendar"].create(
            {"name": "stranded", "company_id": other_company.id, "tz": "UTC"}
        )
        with self.assertRaises(UserError):
            self.env["resource.schedule.exception"].create(
                {
                    "name": "stranded",
                    "calendar_id": other_calendar.id,
                    "resource_id": self._resource(name="Local").id,
                    "date_from": datetime(2026, 3, 2, 8, 0),
                    "date_to": datetime(2026, 3, 2, 17, 0),
                }
            ).flush_recordset()

    def test_global_leave_still_stops_at_a_company_boundary(self):
        other_company = self.env["res.company"].create({"name": "Boundary Co"})
        other_calendar = self.env["resource.calendar"].create(
            {"name": "boundary", "company_id": other_company.id, "tz": "UTC"}
        )
        resource = self._resource(
            name="Boundary", company_id=other_company.id, calendar_id=other_calendar.id
        )
        self._global_leave(self.calendar)
        self.env.flush_all()
        self.assertFalse(
            self._sees_leave(resource),
            "a holiday declared by one named company must not reach another's",
        )

    def test_same_company_leave_is_accepted(self):
        resource = self._resource(name="Same company resource")
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "in company",
                "calendar_id": self.calendar.id,
                "resource_id": resource.id,
                "date_from": datetime(2026, 3, 2, 8, 0),
                "date_to": datetime(2026, 3, 2, 17, 0),
            }
        )
        leave.flush_recordset()
        self.assertEqual(leave.company_id, self.company)
