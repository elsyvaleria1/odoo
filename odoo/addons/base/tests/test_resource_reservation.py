from datetime import UTC, datetime, timedelta

from psycopg.errors import CheckViolation

from odoo.exceptions import UserError, ValidationError
from odoo.libs.datetime import timezone
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import ResourceCase


@tagged("post_install", "-at_install")
class TestResourceReservation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reservation = cls.env["resource.reservation"]

        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Test Calendar", "tz": "UTC"}
        )
        cls.resource_a = cls.env["resource.resource"].create(
            {
                "name": "Resource A",
                "calendar_id": cls.calendar.id,
                "type": "human",
            }
        )
        cls.resource_b = cls.env["resource.resource"].create(
            {
                "name": "Resource B",
                "calendar_id": cls.calendar.id,
                "type": "material",
            }
        )

    def _sync_projection(self, record, vals_list, existing=None):
        return self.Reservation._sync_projection_batch([(record, vals_list, existing)])

    def test_a_new_schedule_moves_the_open_reservations_only(self):
        now = datetime.now().replace(microsecond=0)
        past, coming = self.Reservation.create(
            [
                {
                    "name": name,
                    "resource_id": self.resource_b.id,
                    "date_start": start,
                    "date_end": start + timedelta(days=3),
                }
                for name, start in (
                    ("past", now - timedelta(days=30)),
                    ("coming", now + timedelta(days=30)),
                )
            ]
        )
        past_hours = past.allocated_hours
        around = self.env["resource.calendar"].create(
            {"name": "Around the clock", "schedule_type": "fully_flexible"}
        )
        self.resource_b.calendar_id = around
        self.env.flush_all()
        self.assertEqual(past.resource_calendar_id, self.calendar)
        self.assertEqual(past.allocated_hours, past_hours, "history keeps its share")
        self.assertEqual(coming.resource_calendar_id, around)

    def test_create_reservation(self):
        res = self.Reservation.create(
            {
                "name": "Test reservation",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
            }
        )
        expected = self.calendar.get_work_hours_count(
            datetime(2025, 1, 6, 8, 0), datetime(2025, 1, 6, 17, 0)
        )
        self.assertLess(res.allocated_hours, 9.0)
        self.assertAlmostEqual(res.allocated_hours, expected, places=2)
        self.assertEqual(res.allocated_percentage, 100.0)
        self.assertEqual(res.enforcement_mode, "soft")
        self.assertTrue(res.active)

    def test_no_resource_reservation(self):
        res = self.Reservation.create(
            {
                "name": "Unassigned",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        self.assertEqual(res.schedule_overlap_count, 0)

    def test_date_sanity_start_after_end(self):
        with self.assertRaises(ValidationError):
            self.Reservation.create(
                {
                    "name": "Bad dates",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 17, 0),
                    "date_end": datetime(2025, 1, 6, 8, 0),
                }
            )

    def test_date_sanity_equal_dates_allowed(self):
        res = self.Reservation.create(
            {
                "name": "Zero duration",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 8, 0),
            }
        )
        self.assertTrue(res.id)

    def test_soft_overlap_100_percent(self):
        res1 = self.Reservation.create(
            {
                "name": "Res 1",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "enforcement_mode": "soft",
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "Res 2",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 10, 0),
                "date_end": datetime(2025, 1, 6, 14, 0),
                "enforcement_mode": "soft",
            }
        )
        res1.invalidate_recordset(["schedule_overlap_count"])
        res2.invalidate_recordset(["schedule_overlap_count"])
        self.assertGreater(res1.schedule_overlap_count, 0, "100%+100% should overlap")
        self.assertGreater(res2.schedule_overlap_count, 0)

    def test_no_overlap_50_percent(self):
        res1 = self.Reservation.create(
            {
                "name": "Half 1",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "allocated_percentage": 50.0,
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "Half 2",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "allocated_percentage": 50.0,
            }
        )
        res1.invalidate_recordset(["schedule_overlap_count"])
        res2.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(res1.schedule_overlap_count, 0, "50%+50% should not overlap")
        self.assertEqual(res2.schedule_overlap_count, 0)

    def test_no_overlap_different_resources(self):
        res1 = self.Reservation.create(
            {
                "name": "On A",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "On B",
                "resource_id": self.resource_b.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        res1.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(res1.schedule_overlap_count, 0)
        res2.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(res2.schedule_overlap_count, 0)

    def test_no_overlap_adjacent(self):
        res1 = self.Reservation.create(
            {
                "name": "Morning",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        self.Reservation.create(
            {
                "name": "Afternoon",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 12, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
            }
        )
        res1.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(res1.schedule_overlap_count, 0, "Adjacent should not overlap")

    def test_hard_enforcement_blocks_overlap(self):
        self.Reservation.create(
            {
                "name": "Existing hard",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "enforcement_mode": "hard",
            }
        )
        with self.assertRaises(ValidationError):
            self.Reservation.create(
                {
                    "name": "Conflicting hard",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 10, 0),
                    "date_end": datetime(2025, 1, 6, 14, 0),
                    "enforcement_mode": "hard",
                }
            )

    def test_hard_enforcement_allows_50_percent(self):
        self.Reservation.create(
            {
                "name": "Hard half 1",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "allocated_percentage": 50.0,
                "enforcement_mode": "hard",
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "Hard half 2",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "allocated_percentage": 50.0,
                "enforcement_mode": "hard",
            }
        )
        self.assertTrue(res2.id, "50%+50% hard should be allowed")
        res2.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(
            res2.schedule_overlap_count, 0, "50%+50% must not be a conflict"
        )

    def test_archived_reservation_not_a_conflict(self):
        res1 = self.Reservation.create(
            {
                "name": "Active",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "To be archived",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 9, 0),
                "date_end": datetime(2025, 1, 6, 11, 0),
            }
        )
        self.env.invalidate_all()
        self.assertGreater(res1.schedule_overlap_count, 0, "both active → conflict")

        res2.active = False
        self.env.invalidate_all()
        self.assertEqual(
            res1.schedule_overlap_count,
            0,
            "archived reservation must not be counted as a conflict",
        )
        self.assertEqual(res2.schedule_overlap_count, 0)

    def test_hard_enforcement_ignores_archived(self):
        blocker = self.Reservation.create(
            {
                "name": "Archived blocker",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "enforcement_mode": "hard",
            }
        )
        blocker.active = False
        res = self.Reservation.create(
            {
                "name": "New hard",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 10, 0),
                "date_end": datetime(2025, 1, 6, 14, 0),
                "enforcement_mode": "hard",
            }
        )
        self.assertTrue(res.id)

    def test_hard_enforcement_blocks_unarchive_into_conflict(self):
        blocker = self.Reservation.create(
            {
                "name": "Hard blocker",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "enforcement_mode": "hard",
            }
        )
        blocker.active = False
        self.Reservation.create(
            {
                "name": "Took the slot meanwhile",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 10, 0),
                "date_end": datetime(2025, 1, 6, 14, 0),
            }
        )
        with self.assertRaises(ValidationError):
            blocker.active = True

    def test_hard_enforcement_blocks_mode_switch_into_conflict(self):
        soft = self.Reservation.create(
            {
                "name": "Soft overlapper",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        self.Reservation.create(
            {
                "name": "Other overlapper",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 10, 0),
                "date_end": datetime(2025, 1, 6, 14, 0),
            }
        )
        with self.assertRaises(ValidationError):
            soft.enforcement_mode = "hard"

    def test_cross_origin_overlap(self):
        res1 = self.Reservation.create(
            {
                "name": "From tasks",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "res_model": "project.task",
                "res_id": 1,
            }
        )
        res2 = self.Reservation.create(
            {
                "name": "From appointments",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 10, 0),
                "date_end": datetime(2025, 1, 6, 14, 0),
                "res_model": "calendar.event",
                "res_id": 1,
            }
        )
        res1.invalidate_recordset(["schedule_overlap_count"])
        res2.invalidate_recordset(["schedule_overlap_count"])
        self.assertGreater(
            res1.schedule_overlap_count,
            0,
            "Cross-origin overlap should be detected",
        )

    def test_sync_reservation_create(self):
        partner = self.env["res.partner"].create({"name": "Test Consumer"})
        result = self._sync_projection(
            partner,
            [
                {
                    "name": "Synced reservation",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "resource_id": self.resource_a.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                },
            ],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result.res_model, "res.partner")
        self.assertEqual(result.res_id, partner.id)

    def test_sync_reservation_delete_all(self):
        partner = self.env["res.partner"].create({"name": "Consumer 2"})
        self._sync_projection(
            partner,
            [
                {
                    "name": "To delete",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "resource_id": self.resource_a.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                },
            ],
        )
        result = self._sync_projection(partner, [])
        self.assertEqual(len(result), 0)
        remaining = self.Reservation.search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        self.assertEqual(len(remaining), 0)

    def test_sync_reservation_reconcile(self):
        partner = self.env["res.partner"].create({"name": "Consumer 3"})
        self._sync_projection(
            partner,
            [
                {
                    "name": "On A",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "resource_id": self.resource_a.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                },
            ],
        )
        result = self._sync_projection(
            partner,
            [
                {
                    "name": "On B now",
                    "date_start": datetime(2025, 1, 7, 8, 0),
                    "date_end": datetime(2025, 1, 7, 12, 0),
                    "resource_id": self.resource_b.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                },
            ],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result.resource_id, self.resource_b)
        old = self.Reservation.search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
                ("resource_id", "=", self.resource_a.id),
            ]
        )
        self.assertEqual(len(old), 0)

    def test_sync_reservation_reconciles_duplicate_resource(self):
        partner = self.env["res.partner"].create({"name": "Dup Consumer"})
        self.Reservation.create(
            [
                {
                    "name": f"Dup {i}",
                    "res_model": "res.partner",
                    "res_id": partner.id,
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                }
                for i in range(2)
            ]
        )
        result = self._sync_projection(
            partner,
            [
                {
                    "name": "Only one",
                    "date_start": datetime(2025, 1, 7, 8, 0),
                    "date_end": datetime(2025, 1, 7, 12, 0),
                    "resource_id": self.resource_a.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                },
            ],
        )
        self.assertEqual(len(result), 1)
        remaining = self.Reservation.search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        self.assertEqual(
            len(remaining),
            1,
            "surplus duplicate reservation must be deleted, not orphaned",
        )

    def test_calendar_recomputes_on_company_change(self):
        company_b = self.env["res.company"].create({"name": "Reservation Co B"})
        self.assertNotEqual(
            self.env.company.resource_calendar_id,
            company_b.resource_calendar_id,
            "each company should get its own default calendar",
        )
        res = self.Reservation.create(
            {
                "name": "Company-scoped",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(
            res.resource_calendar_id, self.env.company.resource_calendar_id
        )
        res.company_id = company_b
        self.assertEqual(
            res.resource_calendar_id,
            company_b.resource_calendar_id,
            "calendar must recompute when the company changes",
        )

    def test_cumulative_overlap_three_partial(self):
        reservations = self.Reservation.create(
            [
                {
                    "name": f"Third {i}",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "allocated_percentage": 50.0,
                }
                for i in range(3)
            ]
        )
        self.env.invalidate_all()
        for res in reservations:
            self.assertEqual(
                res.schedule_overlap_count,
                2,
                "each of 3×50% must see the other two as cumulative conflicts",
            )

    def test_cumulative_overlap_below_100_no_conflict(self):
        reservations = self.Reservation.create(
            [
                {
                    "name": f"Small {i}",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "allocated_percentage": 30.0,
                }
                for i in range(3)
            ]
        )
        self.env.invalidate_all()
        for res in reservations:
            self.assertEqual(res.schedule_overlap_count, 0)

    def test_cumulative_overlap_partial_time_window(self):
        a, b, c = self.Reservation.create(
            [
                {
                    "name": "A",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "allocated_percentage": 60.0,
                },
                {
                    "name": "B",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 10, 0),
                    "date_end": datetime(2025, 1, 6, 14, 0),
                    "allocated_percentage": 60.0,
                },
                {
                    "name": "C",
                    "resource_id": self.resource_a.id,
                    "date_start": datetime(2025, 1, 6, 14, 0),
                    "date_end": datetime(2025, 1, 6, 16, 0),
                    "allocated_percentage": 60.0,
                },
            ]
        )
        self.env.invalidate_all()
        self.assertEqual(a.schedule_overlap_count, 1, "A conflicts with B only")
        self.assertEqual(b.schedule_overlap_count, 1, "B conflicts with A only")
        self.assertEqual(c.schedule_overlap_count, 0, "C never exceeds 100%")

    def test_reservation_intervals_batch(self):
        self.Reservation.create(
            {
                "name": "Interval test",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        start_dt = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
        end_dt = datetime(2025, 1, 7, 0, 0, tzinfo=UTC)
        result = self.Reservation._get_reservation_intervals_batch(
            start_dt, end_dt, self.resource_a
        )
        self.assertIn(self.resource_a.id, result)
        intervals = list(result[self.resource_a.id])
        self.assertEqual(len(intervals), 1, "Should return one interval")

    def test_reservation_intervals_batch_empty(self):
        start_dt = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
        end_dt = datetime(2025, 1, 7, 0, 0, tzinfo=UTC)
        result = self.Reservation._get_reservation_intervals_batch(
            start_dt, end_dt, self.resource_a | self.resource_b
        )
        self.assertIn(self.resource_a.id, result)
        self.assertIn(self.resource_b.id, result)
        self.assertEqual(len(list(result[self.resource_a.id])), 0)
        self.assertEqual(len(list(result[self.resource_b.id])), 0)

    def test_action_view_origin(self):
        partner = self.env["res.partner"].create({"name": "Action Test"})
        res = self.Reservation.create(
            {
                "name": "With action",
                "resource_id": self.resource_a.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
                "res_model": "res.partner",
                "res_id": partner.id,
            }
        )
        action = res.action_view_origin()
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], partner.id)


@tagged("post_install", "-at_install")
class TestHardReservationIsUnavailableTime(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Fixed 40h", "tz": "UTC"}
        )
        cls.flexible_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible",
                "schedule_type": "flexible",
                "hours_per_week": 40,
                "hours_per_day": 8,
                "tz": "UTC",
            }
        )
        cls.machine = cls.env["resource.resource"].create(
            {
                "name": "Machine",
                "type": "material",
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )
        cls.flexible = cls.env["resource.resource"].create(
            {
                "name": "Flexible machine",
                "type": "material",
                "calendar_id": cls.flexible_calendar.id,
                "tz": "UTC",
            }
        )
        # Monday 2025-01-06, calendar attends 08:00-12:00 and 13:00-17:00.
        cls.day_start = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
        cls.day_end = datetime(2025, 1, 7, 0, 0, tzinfo=UTC)

    def _book(self, resource, mode, start=(9, 0), end=(11, 0)):
        return self.env["resource.reservation"].create(
            {
                "name": f"{mode} booking",
                "resource_id": resource.id,
                "date_start": datetime(2025, 1, 6, *start),
                "date_end": datetime(2025, 1, 6, *end),
                "enforcement_mode": mode,
            }
        )

    def _work_hours(self, resource, exclude_bookings=True):
        intervals = self.calendar._work_intervals_batch(
            self.day_start, self.day_end, resource, exclude_bookings=exclude_bookings
        )[resource.id]
        return (
            sum((stop - start).total_seconds() for start, stop, _m in intervals) / 3600
        )

    def test_soft_reservation_leaves_work_time_intact(self):
        self._book(self.machine, "soft")
        self.assertEqual(self._work_hours(self.machine), 8.0)

    def test_hard_reservation_is_subtracted_from_free_time(self):
        self._book(self.machine, "hard")
        self.assertEqual(self._work_hours(self.machine), 6.0)
        self.assertEqual(self._work_hours(self.machine, exclude_bookings=False), 8.0)

    def test_hard_reservation_outside_attendance_costs_nothing(self):
        self._book(self.machine, "hard", start=(18, 0), end=(22, 0))
        self.assertEqual(self._work_hours(self.machine), 8.0)

    def test_archived_hard_reservation_is_ignored(self):
        self._book(self.machine, "hard").action_archive()
        self.assertEqual(self._work_hours(self.machine), 8.0)

    def test_compute_leaves_false_ignores_hard_reservations(self):
        self._book(self.machine, "hard")
        intervals = self.calendar._work_intervals_batch(
            self.day_start, self.day_end, self.machine, compute_leaves=False
        )[self.machine.id]
        hours = sum((stop - start).total_seconds() for start, stop, _m in intervals)
        self.assertEqual(hours / 3600, 8.0)

    def test_hard_reservation_is_unavailable_for_a_fixed_resource(self):
        self._book(self.machine, "hard")
        unavailable = self.calendar._unavailable_intervals_batch(
            self.day_start, self.day_end, self.machine
        )[self.machine.id]
        self.assertIn(
            (
                datetime(2025, 1, 6, 9, 0, tzinfo=UTC),
                datetime(2025, 1, 6, 11, 0, tzinfo=UTC),
            ),
            unavailable,
        )

    def test_hard_reservation_is_unavailable_for_a_flexible_resource(self):
        self._book(self.flexible, "hard")
        unavailable = self.flexible_calendar._unavailable_intervals_batch(
            self.day_start, self.day_end, self.flexible
        )[self.flexible.id]
        self.assertEqual(
            unavailable,
            [
                (
                    datetime(2025, 1, 6, 9, 0, tzinfo=UTC),
                    datetime(2025, 1, 6, 11, 0, tzinfo=UTC),
                )
            ],
        )

    def test_resource_level_unavailability_sees_the_booking(self):
        self._book(self.machine, "hard")
        result = self.machine._get_unavailable_intervals(self.day_start, self.day_end)
        self.assertTrue(
            any(
                start.hour == 9 and stop.hour == 11
                for start, stop in result[self.machine.id]
            )
        )

    def test_other_resource_is_untouched(self):
        self._book(self.machine, "hard")
        self.assertEqual(self._work_hours(self.flexible), 8.0)

    def test_company_wide_window_has_no_reservations(self):
        self._book(self.machine, "hard")
        empty = self.env["resource.resource"]
        intervals = self.calendar._work_intervals_batch(self.day_start, self.day_end)[
            empty.id
        ]
        hours = sum((stop - start).total_seconds() for start, stop, _m in intervals)
        self.assertEqual(hours / 3600, 8.0)


@tagged("post_install", "-at_install")
class TestResourceCapacity(TransactionCase):
    def test_default_capacity_is_one(self):
        resource = self.env["resource.resource"].create(
            {"name": "Desk", "type": "material", "tz": "UTC"}
        )
        self.assertEqual(resource.capacity, 1)

    def test_capacity_must_be_positive(self):
        from odoo.tools import mute_logger

        with (
            self.assertRaises(CheckViolation),
            mute_logger("odoo.sql_db", "odoo.db.cursor"),
        ):
            with self.env.cr.savepoint():
                self.env["resource.resource"].create(
                    {
                        "name": "Void",
                        "type": "material",
                        "tz": "UTC",
                        "capacity": 0,
                    }
                )


@tagged("post_install", "-at_install")
class TestResourceFreeWindow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Resource = cls.env["resource.resource"]
        cls.press = Resource.create({"name": "Press", "type": "material", "tz": "UTC"})
        cls.crane = Resource.create({"name": "Crane", "type": "material", "tz": "UTC"})

    def _book(self, resource, start, end, mode="soft"):
        return self.env["resource.reservation"].create(
            {
                "name": "Busy",
                "resource_id": resource.id,
                "date_start": start,
                "date_end": end,
                "enforcement_mode": mode,
            }
        )

    def test_a_free_window_is_the_one_asked_for(self):
        start = datetime(2026, 5, 4, 8)
        self.assertEqual(
            (self.press | self.crane)._find_free_window(start, 2),
            (start, datetime(2026, 5, 4, 10)),
        )

    def test_the_window_steps_past_every_booking_of_every_resource(self):
        self._book(self.press, datetime(2026, 5, 4, 7), datetime(2026, 5, 4, 9))
        self._book(self.crane, datetime(2026, 5, 4, 9), datetime(2026, 5, 4, 12))
        self.assertEqual(
            (self.press | self.crane)._find_free_window(datetime(2026, 5, 4, 8), 2),
            (datetime(2026, 5, 4, 12), datetime(2026, 5, 4, 14)),
        )

    def test_an_archived_booking_does_not_count(self):
        booking = self._book(
            self.press, datetime(2026, 5, 4, 8), datetime(2026, 5, 4, 10)
        )
        booking.active = False
        start = datetime(2026, 5, 4, 8)
        self.assertEqual(self.press._find_free_window(start, 1)[0], start)

    def test_no_window_within_the_horizon_is_none(self):
        self._book(self.press, datetime(2026, 5, 4), datetime(2026, 5, 10))
        self.assertIsNone(
            self.press._find_free_window(datetime(2026, 5, 4), 1, horizon_days=3)
        )


@tagged("post_install", "-at_install")
class TestReservationUTCConversion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reservation = cls.env["resource.reservation"]
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "UTC Calendar", "tz": "UTC"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Test Resource",
                "calendar_id": cls.calendar.id,
            }
        )

    def test_intervals_with_non_utc_query(self):
        self.Reservation.create(
            {
                "name": "Morning slot",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        tokyo = timezone("Asia/Tokyo")
        start = datetime(2025, 1, 6, 0, 0).replace(tzinfo=tokyo)
        end = datetime(2025, 1, 7, 0, 0).replace(tzinfo=tokyo)
        result = self.Reservation._get_reservation_intervals_batch(
            start, end, self.resource
        )
        intervals = list(result[self.resource.id])
        self.assertEqual(len(intervals), 1, "Should find the reservation in this range")


class TestReservationCompanyIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.ref("base.main_company")
        cls.company_b = cls.env["res.company"].create({"name": "Company B"})
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Company A machine",
                "company_id": cls.company_a.id,
                "calendar_id": cls.company_a.resource_calendar_id.id,
                "tz": "UTC",
            }
        )

    def test_company_follows_the_resource(self):
        reservation = (
            self.env["resource.reservation"]
            .with_company(self.company_b)
            .create(
                {
                    "name": "Booking",
                    "resource_id": self.resource.id,
                    "date_start": datetime(2025, 9, 9, 8),
                    "date_end": datetime(2025, 9, 9, 17),
                }
            )
        )
        self.assertEqual(reservation.company_id, self.company_a)

    def test_mismatched_company_is_rejected(self):
        with self.assertRaises(UserError):
            self.env["resource.reservation"].create(
                {
                    "name": "Cross company",
                    "resource_id": self.resource.id,
                    "company_id": self.company_b.id,
                    "date_start": datetime(2025, 9, 9, 8),
                    "date_end": datetime(2025, 9, 9, 17),
                }
            )


class TestHardEnforcementProtectsItsSlot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reservation = cls.env["resource.reservation"]
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Protected machine",
                "calendar_id": cls.env.ref("base.resource_calendar_std").id,
                "tz": "UTC",
            }
        )

    def _hard(self):
        return self.Reservation.create(
            {
                "name": "Maintenance",
                "resource_id": self.resource.id,
                "enforcement_mode": "hard",
                "date_start": datetime(2025, 6, 2, 8),
                "date_end": datetime(2025, 6, 2, 17),
            }
        )

    def test_soft_cannot_be_created_over_a_hard_slot(self):
        self._hard()
        with self.assertRaises(ValidationError):
            self.Reservation.create(
                {
                    "name": "Ordinary task",
                    "resource_id": self.resource.id,
                    "date_start": datetime(2025, 6, 2, 10),
                    "date_end": datetime(2025, 6, 2, 14),
                }
            )

    def test_soft_cannot_be_moved_onto_a_hard_slot(self):
        self._hard()
        mover = self.Reservation.create(
            {
                "name": "Ordinary task",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 6, 3, 8),
                "date_end": datetime(2025, 6, 3, 17),
            }
        )
        with self.assertRaises(ValidationError):
            mover.write(
                {
                    "date_start": datetime(2025, 6, 2, 10),
                    "date_end": datetime(2025, 6, 2, 14),
                }
            )

    def test_partial_allocations_still_fit(self):
        self.Reservation.create(
            {
                "name": "Half hard",
                "resource_id": self.resource.id,
                "enforcement_mode": "hard",
                "allocated_percentage": 50.0,
                "date_start": datetime(2025, 6, 4, 8),
                "date_end": datetime(2025, 6, 4, 17),
            }
        )
        other = self.Reservation.create(
            {
                "name": "Other half",
                "resource_id": self.resource.id,
                "allocated_percentage": 50.0,
                "date_start": datetime(2025, 6, 4, 8),
                "date_end": datetime(2025, 6, 4, 17),
            }
        )
        self.assertTrue(other.id)

    def test_adjacent_booking_is_not_a_conflict(self):
        self._hard()
        adjacent = self.Reservation.create(
            {
                "name": "Right after",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 6, 2, 17),
                "date_end": datetime(2025, 6, 2, 19),
            }
        )
        self.assertTrue(adjacent.id)

    def test_archived_hard_does_not_block(self):
        blocker = self._hard()
        blocker.active = False
        allowed = self.Reservation.create(
            {
                "name": "Now free",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 6, 2, 10),
                "date_end": datetime(2025, 6, 2, 14),
            }
        )
        self.assertTrue(allowed.id)


class TestOverlapSweep(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reservation = cls.env["resource.reservation"]
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Swept",
                "calendar_id": cls.env.ref("base.resource_calendar_std").id,
                "tz": "UTC",
            }
        )

    def _make(self, day, hour_from, hour_to, pct=100.0):
        return self.Reservation.create(
            {
                "name": f"r{day}-{hour_from}",
                "resource_id": self.resource.id,
                "allocated_percentage": pct,
                "date_start": datetime(2025, 1, day, hour_from),
                "date_end": datetime(2025, 1, day, hour_to),
            }
        )

    def test_zero_length_reservation_covers_nothing(self):
        first = self._make(9, 8, 17)
        self._make(9, 10, 10)
        first.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(first.schedule_overlap_count, 0)

    def test_distant_history_is_not_scanned(self):
        self.Reservation.create(
            [
                {
                    "name": f"ancient{index}",
                    "resource_id": self.resource.id,
                    "date_start": datetime(2000, 1, 1, 8) + timedelta(days=index),
                    "date_end": datetime(2000, 1, 1, 17) + timedelta(days=index),
                }
                for index in range(5)
            ]
        )
        recent = self._make(10, 8, 17)
        recent.invalidate_recordset(["schedule_overlap_count"])
        self.assertEqual(recent.schedule_overlap_count, 0)


class TestAllocatedHoursBatching(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env.ref("base.resource_calendar_std")

    def test_batch_matches_one_by_one(self):
        resources = self.env["resource.resource"].create(
            [
                {"name": f"R{index}", "calendar_id": self.calendar.id, "tz": "UTC"}
                for index in range(5)
            ]
        )
        vals = [
            {
                "name": f"b{index}",
                "resource_id": resource.id,
                "date_start": datetime(2025, 3, 3, 9) + timedelta(days=index),
                "date_end": datetime(2025, 3, 3, 17) + timedelta(days=index),
            }
            for index, resource in enumerate(resources)
        ]
        batched = self.env["resource.reservation"].create(vals)
        one_by_one = [
            self.env["resource.reservation"].create(
                dict(entry, name=f"{entry['name']}s")
            )
            for entry in vals
        ]
        self.assertEqual(
            batched.mapped("allocated_hours"),
            [record.allocated_hours for record in one_by_one],
        )

    def test_flexible_batch_matches_one_by_one(self):
        flexible = self.env["resource.calendar"].create(
            {
                "name": "Flexible 30h",
                "schedule_type": "flexible",
                "hours_per_week": 30,
                "hours_per_day": 8,
            }
        )
        windows = [
            (datetime(2026, 6, 3), datetime(2026, 6, 10)),
            (datetime(2026, 6, 8, 9), datetime(2026, 6, 12, 17)),
            (datetime(2026, 6, 11, 9), datetime(2026, 6, 11, 13)),
            (datetime(2026, 6, 13), datetime(2026, 6, 16)),
        ]

        def vals_for(suffix):
            resources = self.env["resource.resource"].create(
                [
                    {"name": f"UTC {suffix}", "calendar_id": flexible.id, "tz": "UTC"},
                    {
                        "name": f"Mexico {suffix}",
                        "calendar_id": flexible.id,
                        "tz": "America/Mexico_City",
                    },
                ]
            )
            return [
                {
                    "name": f"{resource.name} {start}",
                    "resource_id": resource.id,
                    "date_start": start,
                    "date_end": stop,
                }
                for resource in resources
                for start, stop in windows
            ]

        batched = self.env["resource.reservation"].create(vals_for("batch"))
        one_by_one = [
            self.env["resource.reservation"].create(entry)
            for entry in reversed(vals_for("alone"))
        ][::-1]
        self.env.flush_all()
        self.assertEqual(
            batched.mapped("allocated_hours"),
            [record.allocated_hours for record in one_by_one],
        )
        self.assertTrue(any(batched.mapped("allocated_hours")))

    def test_percentage_is_applied(self):
        resource = self.env["resource.resource"].create(
            {"name": "Half", "calendar_id": self.calendar.id, "tz": "UTC"}
        )
        full = self.env["resource.reservation"].create(
            {
                "name": "full",
                "resource_id": resource.id,
                "date_start": datetime(2025, 3, 3, 8),
                "date_end": datetime(2025, 3, 3, 17),
            }
        )
        half = self.env["resource.reservation"].create(
            {
                "name": "half",
                "resource_id": resource.id,
                "allocated_percentage": 50.0,
                "date_start": datetime(2025, 3, 4, 8),
                "date_end": datetime(2025, 3, 4, 17),
            }
        )
        self.assertAlmostEqual(half.allocated_hours, full.allocated_hours / 2, places=2)

    def test_undated_reservation_is_zero(self):
        resource = self.env["resource.resource"].create(
            {"name": "Undated", "calendar_id": self.calendar.id, "tz": "UTC"}
        )
        reservation = self.env["resource.reservation"].create(
            {"name": "undated", "resource_id": resource.id}
        )
        self.assertEqual(reservation.allocated_hours, 0.0)

    def test_zero_percentage_books_no_hours(self):
        resource = self.env["resource.resource"].create(
            {"name": "Idle", "calendar_id": self.calendar.id, "tz": "UTC"}
        )
        reservation = self.env["resource.reservation"].create(
            {
                "name": "zero",
                "resource_id": resource.id,
                "allocated_percentage": 0.0,
                "date_start": datetime(2025, 3, 3, 8),
                "date_end": datetime(2025, 3, 3, 17),
            }
        )
        self.assertEqual(reservation.allocated_hours, 0.0, "0 % is no hours, not 100 %")


@tagged("post_install", "-at_install")
class TestAllocatedPercentageBounds(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Bounds", "tz": "UTC"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Bounded", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.slot = {
            "date_start": datetime(2025, 7, 1, 8),
            "date_end": datetime(2025, 7, 1, 12),
        }

    def _reservation(self, name, **extra):
        return self.env["resource.reservation"].create(
            {"name": name, "resource_id": self.resource.id, **self.slot, **extra}
        )

    @mute_logger("odoo.db.cursor")
    def test_negative_percentage_rejected(self):
        with self.assertRaises(CheckViolation), self.env.cr.savepoint(flush=False):
            self._reservation("negative", allocated_percentage=-100.0)

    @mute_logger("odoo.db.cursor")
    def test_nonfinite_percentage_rejected(self):
        for percentage in (float("inf"), float("nan")):
            with (
                self.subTest(percentage=percentage),
                self.assertRaises(CheckViolation),
                self.env.cr.savepoint(flush=False),
            ):
                self._reservation("nonfinite", allocated_percentage=percentage)

    def test_boundaries_accepted(self):
        self.assertTrue(self._reservation("zero", allocated_percentage=0.0))
        self.assertTrue(self._reservation("full", allocated_percentage=100.0))

    def test_hard_enforcement_cannot_be_cancelled_out(self):
        umbrella = self.env["resource.reservation"].create(
            {
                "name": "umbrella",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 7, 1, 0),
                "date_end": datetime(2025, 7, 2, 0),
                "allocated_percentage": 0.0,
            }
        )
        self._reservation("hard", enforcement_mode="hard")
        self.env.flush_all()
        self.env.cr.execute(
            "ALTER TABLE resource_reservation"
            " DROP CONSTRAINT resource_reservation_check_allocated_percentage"
        )
        self.env.cr.execute(
            "UPDATE resource_reservation SET allocated_percentage = -100 WHERE id = %s",
            (umbrella.id,),
        )
        self.env.invalidate_all()
        with self.assertRaises(ValidationError):
            self._reservation("intruder", allocated_percentage=100.0)


@tagged("post_install", "-at_install")
class TestReservationCalendarOverride(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Calendar = cls.env["resource.calendar"]
        cls.full = Calendar.create({"name": "Full 8h", "tz": "UTC"})
        cls.half = Calendar.create(
            {
                "name": "Half 4h",
                "tz": "UTC",
                "attendance_ids": [(5, 0, 0)]
                + [
                    (
                        0,
                        0,
                        {
                            "name": f"day{day}",
                            "dayofweek": str(day),
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    )
                    for day in range(5)
                ],
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Overridable", "calendar_id": cls.full.id, "tz": "UTC"}
        )
        cls.window = {
            "date_start": datetime(2025, 1, 6),
            "date_end": datetime(2025, 1, 7),
        }

    def test_override_is_honoured_with_a_resource(self):
        reservation = self.env["resource.reservation"].create(
            {
                "name": "override",
                "resource_id": self.resource.id,
                "resource_calendar_id": self.half.id,
                **self.window,
            }
        )
        self.assertEqual(reservation.allocated_hours, 4.0)

    def test_resource_calendar_used_when_not_overridden(self):
        reservation = self.env["resource.reservation"].create(
            {"name": "native", "resource_id": self.resource.id, **self.window}
        )
        self.assertEqual(reservation.resource_calendar_id, self.full)
        self.assertEqual(reservation.allocated_hours, 8.0)

    def test_override_still_honoured_without_a_resource(self):
        reservation = self.env["resource.reservation"].create(
            {
                "name": "calendar only",
                "resource_calendar_id": self.half.id,
                **self.window,
            }
        )
        self.assertEqual(reservation.allocated_hours, 4.0)

    def test_mixed_batch_resolves_each_record_on_its_own_calendar(self):
        Reservation = self.env["resource.reservation"]
        overridden = Reservation.create(
            {
                "name": "o",
                "resource_id": self.resource.id,
                "resource_calendar_id": self.half.id,
                **self.window,
            }
        )
        native = Reservation.create(
            {"name": "n", "resource_id": self.resource.id, **self.window}
        )
        (overridden | native).invalidate_recordset(["allocated_hours"])
        (overridden | native)._compute_allocated_hours()
        self.assertEqual(overridden.allocated_hours, 4.0)
        self.assertEqual(native.allocated_hours, 8.0)


@tagged("post_install", "-at_install")
class TestOriginDisplayAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Origin", "tz": "UTC"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Origin res", "calendar_id": cls.calendar.id, "tz": "UTC"}
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "Origin reader",
                "login": "origin_reader",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _reservation(self, res_model, res_id, day):
        return self.env["resource.reservation"].create(
            {
                "name": "origin probe",
                "resource_id": self.resource.id,
                "res_model": res_model,
                "res_id": res_id,
                "date_start": datetime(2025, 5, day, 8),
                "date_end": datetime(2025, 5, day, 12),
            }
        )

    def test_unreadable_source_falls_back_to_raw_reference(self):
        parameter = self.env["ir.config_parameter"].create(
            {"key": "resource.secret", "value": "secret"}
        )
        reservation = self._reservation("ir.config_parameter", parameter.id, 1)
        reservation.invalidate_recordset(["origin_display"])
        self.assertEqual(
            reservation.with_user(self.user).origin_display,
            f"ir.config_parameter,{parameter.id}",
        )

    def test_readable_source_still_resolves(self):
        partner = self.env["res.partner"].create({"name": "Visible Partner"})
        reservation = self._reservation("res.partner", partner.id, 2)
        reservation.invalidate_recordset(["origin_display"])
        self.assertEqual(
            reservation.with_user(self.user).origin_display, "Visible Partner"
        )

    def test_deleted_source_still_falls_back(self):
        reservation = self._reservation("res.partner", 99999999, 3)
        reservation.invalidate_recordset(["origin_display"])
        self.assertEqual(
            reservation.with_user(self.user).origin_display, "res.partner,99999999"
        )

    def test_uninstalled_model_still_falls_back(self):
        reservation = self._reservation("no.such.model", 7, 4)
        reservation.invalidate_recordset(["origin_display"])
        self.assertEqual(reservation.origin_display, "no.such.model,7")

    def test_no_source_means_no_origin(self):
        reservation = self.env["resource.reservation"].create(
            {
                "name": "no origin",
                "resource_id": self.resource.id,
                "date_start": datetime(2025, 5, 5, 8),
                "date_end": datetime(2025, 5, 5, 12),
            }
        )
        self.assertFalse(reservation.origin_display)


@tagged("post_install", "-at_install")
class TestOverlapSweepInSql(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Lathe", "tz": "UTC"}
        )
        cls.Reservation = cls.env["resource.reservation"]
        cls.booked = cls.Reservation.create(
            {
                "name": "booked",
                "resource_id": cls.resource.id,
                "date_start": datetime(2026, 6, 1, 8),
                "date_end": datetime(2026, 6, 1, 12),
                "allocated_percentage": 60,
            }
        )

    def test_prospective_conflicts_accept_string_datetimes(self):
        conflicts = self.Reservation._get_prospective_conflicts(
            [
                {
                    "resource_id": self.resource.id,
                    "date_start": "2026-06-01 10:00:00",
                    "date_end": "2026-06-01 11:00:00",
                    "allocated_percentage": 50,
                }
            ]
        )
        self.assertEqual(conflicts, self.booked)

    def test_prospective_within_capacity_is_not_a_conflict(self):
        conflicts = self.Reservation._get_prospective_conflicts(
            [
                {
                    "resource_id": self.resource.id,
                    "date_start": datetime(2026, 6, 1, 10),
                    "date_end": datetime(2026, 6, 1, 11),
                    "allocated_percentage": 40,
                }
            ]
        )
        self.assertFalse(conflicts)

    def test_search_operators_agree_with_the_compute(self):
        other = self.Reservation.create(
            {
                "name": "clash",
                "resource_id": self.resource.id,
                "date_start": datetime(2026, 6, 1, 9),
                "date_end": datetime(2026, 6, 1, 10),
            }
        )
        self.assertEqual(self.booked.schedule_overlap_count, 1)
        self.assertEqual(
            self.Reservation.search([("schedule_overlap_count", ">=", 1)]),
            self.booked | other,
        )
        self.assertNotIn(
            self.booked, self.Reservation.search([("schedule_overlap_count", "<", 1)])
        )


class TestReservationScheduling(ResourceCase):
    def test_allocation_mixin_triggers_on_allocated_percentage(self):
        projection = self.env["mixin.resource.scheduling"]._get_fields_sync_trigger()
        self.assertNotIn("allocated_percentage", projection)

        allocation = self.env["mixin.resource.allocation"]._get_fields_sync_trigger()
        self.assertIn("allocated_percentage", allocation)

    def test_calendar_override_applies_to_a_flexible_resource(self):
        flexible = self.env["resource.calendar"].create(
            {
                "name": "flex 20h",
                "company_id": self.company.id,
                "tz": "UTC",
                "schedule_type": "flexible",
                "hours_per_week": 20.0,
                "hours_per_day": 4.0,
            }
        )
        resource = self._resource(name="Flexible", calendar_id=flexible.id)
        reservation = self.env["resource.reservation"].create(
            {
                "name": "override me",
                "resource_id": resource.id,
                "date_start": datetime(2026, 3, 2, 0, 0),
                "date_end": datetime(2026, 3, 6, 23, 59),
            }
        )
        native = reservation._scheduling_get_work_hours(
            reservation.date_start, reservation.date_end, resource=resource
        )
        overridden = reservation._scheduling_get_work_hours(
            reservation.date_start,
            reservation.date_end,
            resource=resource,
            calendar=self.calendar,
        )
        self.assertNotEqual(
            native,
            overridden,
            "an explicit calendar must override the resource's own, on every path",
        )
        self.assertEqual(overridden, 40.0)

    def _conflicting_pair(self):
        resource = self._resource(name="Double booked")
        vals = {
            "resource_id": resource.id,
            "date_start": datetime(2026, 3, 2, 8, 0),
            "date_end": datetime(2026, 3, 2, 12, 0),
        }
        first = self.env["resource.reservation"].create({"name": "first", **vals})
        second = self.env["resource.reservation"].create({"name": "second", **vals})
        return first, second

    def test_conflicts_are_searchable(self):
        first, second = self._conflicting_pair()
        found = self.env["resource.reservation"].search(
            [("schedule_overlap_count", ">", 0)]
        )
        self.assertLessEqual({first.id, second.id}, set(found.ids))

    def test_conflict_free_reservations_are_searchable_too(self):
        first, _second = self._conflicting_pair()
        alone = self.env["resource.reservation"].create(
            {
                "name": "alone",
                "resource_id": self._resource(name="Solo").id,
                "date_start": datetime(2026, 3, 3, 8, 0),
                "date_end": datetime(2026, 3, 3, 12, 0),
            }
        )
        clean = self.env["resource.reservation"].search(
            [("schedule_overlap_count", "=", 0)]
        )
        self.assertIn(alone.id, clean.ids)
        self.assertNotIn(first.id, clean.ids)

    def test_search_and_compute_agree(self):
        first, second = self._conflicting_pair()
        for reservation in (first, second):
            found = self.env["resource.reservation"].search(
                [
                    ("id", "=", reservation.id),
                    ("schedule_overlap_count", "=", reservation.schedule_overlap_count),
                ]
            )
            self.assertEqual(found, reservation)
