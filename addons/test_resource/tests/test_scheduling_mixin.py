from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.base.tests.common import ResourceCase


@tagged("post_install", "-at_install")
class TestSchedulingMixin(TransactionCase):
    """Test the resource scheduling mixin fields and methods.

    Uses a standard 40h/week calendar (Mon-Fri, 8:00-12:00 + 13:00-17:00 UTC)
    and various resource configurations to validate the consolidated scheduling
    logic.

    Reference dates (2025):
        Mon 2025-01-06  |  Tue 2025-01-07  |  Wed 2025-01-08
        Thu 2025-01-09  |  Fri 2025-01-10  |  Sat 2025-01-11
        Sun 2025-01-12  |  Mon 2025-01-13
    """

    MODEL_NAME = "resource.scheduling.test"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Test 40h Calendar",
                "tz": "UTC",
            }
        )

        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Test Resource",
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )

        cls.flex_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Flexible 35h Calendar",
                "tz": "UTC",
                "schedule_type": "flexible",
                "hours_per_day": 7.0,
                "full_time_required_hours": 35,
            }
        )
        cls.flex_resource = cls.env["resource.resource"].create(
            {
                "name": "Flex Resource",
                "calendar_id": cls.flex_calendar.id,
                "tz": "UTC",
            }
        )

        cls.fully_flex_resource = cls.env["resource.resource"].create(
            {
                "name": "Fully Flex Resource",
                "calendar_id": False,
                "tz": "UTC",
            }
        )

        cls.Model = cls.env[cls.MODEL_NAME]


    def test_allocated_hours_with_calendar(self):
        record = self.Model.create(
            {
                "name": "Single day",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 8.0)

    def test_allocated_hours_cross_day(self):
        record = self.Model.create(
            {
                "name": "Cross day",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 7, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 16.0)

    def test_allocated_hours_cross_weekend(self):
        record = self.Model.create(
            {
                "name": "Cross weekend",
                "date_start": datetime(2025, 1, 10, 8, 0),
                "date_end": datetime(2025, 1, 13, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 16.0)

    def test_allocated_hours_no_resource(self):
        record = self.Model.create(
            {
                "name": "No resource",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
            }
        )
        self.assertFalse(record.resource_id)
        expected = self.env.company.resource_calendar_id.get_work_hours_count(
            datetime(2025, 1, 6, 8, 0),
            datetime(2025, 1, 6, 17, 0),
        )
        self.assertLess(record.allocated_hours, 9.0)
        self.assertAlmostEqual(record.allocated_hours, expected, places=2)

    def test_allocated_hours_flexible_resource(self):
        record = self.Model.create(
            {
                "name": "Flexible",
                "date_start": datetime(2025, 1, 6, 0, 0),
                "date_end": datetime(2025, 1, 10, 23, 59),
                "resource_id": self.flex_resource.id,
            }
        )
        self.assertAlmostEqual(record.allocated_hours, 35.0, places=0)

    def test_allocated_percentage(self):
        record = self.Model.create(
            {
                "name": "50% allocation",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 50.0,
            }
        )
        self.assertEqual(record.allocated_hours, 4.0)


    def test_overlap_detection(self):
        rec1 = self.Model.create(
            {
                "name": "Slot A",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 100.0,
            }
        )
        rec2 = self.Model.create(
            {
                "name": "Slot B",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 100.0,
            }
        )
        self.env.invalidate_all()
        self.assertGreater(rec1.schedule_overlap_count, 0)
        self.assertGreater(rec2.schedule_overlap_count, 0)

    def test_overlap_percentage(self):
        rec1 = self.Model.create(
            {
                "name": "Slot 50A",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 50.0,
            }
        )
        rec2 = self.Model.create(
            {
                "name": "Slot 50B",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 50.0,
            }
        )
        self.env.invalidate_all()
        self.assertEqual(rec1.schedule_overlap_count, 0)
        self.assertEqual(rec2.schedule_overlap_count, 0)

        rec1.allocated_percentage = 60.0
        rec2.allocated_percentage = 60.0
        self.env.invalidate_all()
        self.assertGreater(rec1.schedule_overlap_count, 0)
        self.assertGreater(rec2.schedule_overlap_count, 0)

    def test_no_overlap_different_resource(self):
        resource2 = self.env["resource.resource"].create(
            {
                "name": "Other Resource",
                "calendar_id": self.calendar.id,
                "tz": "UTC",
            }
        )
        rec1 = self.Model.create(
            {
                "name": "Resource 1 slot",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 100.0,
            }
        )
        rec2 = self.Model.create(
            {
                "name": "Resource 2 slot",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": resource2.id,
                "allocated_percentage": 100.0,
            }
        )
        self.env.invalidate_all()
        self.assertEqual(rec1.schedule_overlap_count, 0)
        self.assertEqual(rec2.schedule_overlap_count, 0)


    def _manual_vals(self, **overrides):
        vals = {
            "name": "Manual",
            "date_start": datetime(2025, 1, 6, 8, 0),
            "date_end": datetime(2025, 1, 6, 17, 0),
            "resource_id": self.resource.id,
        }
        vals.update(overrides)
        return vals

    def test_manual_sync_skips_the_create_hook(self):
        Manual = self.env["resource.scheduling.manual.test"]
        record = Manual.create(self._manual_vals())
        self.assertFalse(
            record.reservation_ids,
            "create must not project for a consumer that manages its own sync",
        )

        record._sync_reservations()
        self.assertEqual(len(record.reservation_ids), 1)
        self.assertEqual(record.reservation_ids.date_start, datetime(2025, 1, 6, 8, 0))

    def test_manual_sync_skips_the_write_hook(self):
        Manual = self.env["resource.scheduling.manual.test"]
        record = Manual.create(self._manual_vals())
        record._sync_reservations()

        record.date_end = datetime(2025, 1, 6, 12, 0)
        self.assertEqual(
            record.reservation_ids.date_end,
            datetime(2025, 1, 6, 17, 0),
            "the ledger still holds the pre-write window",
        )

        record._sync_reservations()
        self.assertEqual(record.reservation_ids.date_end, datetime(2025, 1, 6, 12, 0))

    def test_automatic_sync_remains_the_default(self):
        record = self.Model.create(self._manual_vals())
        self.assertEqual(
            len(record.reservation_ids),
            1,
            "consumers that do not set the flag keep the CRUD hooks",
        )

    def test_manual_sync_unlink_still_cleans_the_ledger(self):
        Manual = self.env["resource.scheduling.manual.test"]
        record = Manual.create(self._manual_vals())
        record._sync_reservations()
        reservation = record.reservation_ids
        self.assertTrue(reservation.exists())

        record.unlink()
        self.assertFalse(
            reservation.exists(),
            "a deleted consumer must never leave a claim behind, however it syncs",
        )


    def _booked_day(self, percentage=100.0, name="Booked"):
        return self.Model.create(
            {
                "name": name,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": percentage,
            }
        )

    def test_unsaved_record_sees_conflict(self):
        self._booked_day()
        self.env.invalidate_all()
        draft = self.Model.new(
            {
                "name": "Draft",
                "date_start": datetime(2025, 1, 6, 9, 0),
                "date_end": datetime(2025, 1, 6, 11, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 100.0,
            }
        )
        self.assertGreater(
            draft.schedule_overlap_count,
            0,
            "the warning must appear before the double booking is committed",
        )

    def test_unsaved_record_free_window_is_clean(self):
        self._booked_day()
        self.env.invalidate_all()
        draft = self.Model.new(
            {
                "name": "Draft",
                "date_start": datetime(2025, 1, 7, 9, 0),
                "date_end": datetime(2025, 1, 7, 11, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 100.0,
            }
        )
        self.assertEqual(draft.schedule_overlap_count, 0)

    def test_unsaved_record_conflict_is_cumulative(self):
        self._booked_day(percentage=50.0, name="Half A")
        self._booked_day(percentage=50.0, name="Half B")
        self.env.invalidate_all()
        draft = self.Model.new(
            {
                "name": "Third half",
                "date_start": datetime(2025, 1, 6, 9, 0),
                "date_end": datetime(2025, 1, 6, 11, 0),
                "resource_id": self.resource.id,
                "allocated_percentage": 50.0,
            }
        )
        self.assertGreater(draft.schedule_overlap_count, 0)

    def test_unsaved_record_without_resource_is_clean(self):
        self._booked_day()
        self.env.invalidate_all()
        draft = self.Model.new(
            {
                "name": "Open",
                "date_start": datetime(2025, 1, 6, 9, 0),
                "date_end": datetime(2025, 1, 6, 11, 0),
                "allocated_percentage": 100.0,
            }
        )
        self.assertEqual(draft.schedule_overlap_count, 0)

    def test_saved_record_conflicts_exclude_its_own_bookings(self):
        first = self._booked_day(name="First")
        second = self._booked_day(name="Second")
        self.env.invalidate_all()

        conflicts = first._get_schedule_conflicts_batch()[first.id]
        self.assertTrue(conflicts, "the two full-day bookings collide")
        self.assertNotIn(
            first.reservation_ids.id,
            conflicts.ids,
            "a record must never be reported as conflicting with itself",
        )
        self.assertEqual(conflicts.ids, second.reservation_ids.ids)

    def test_unsaved_record_conflicts_match_once_saved(self):
        self._booked_day()
        self.env.invalidate_all()
        values = {
            "name": "Draft",
            "date_start": datetime(2025, 1, 6, 9, 0),
            "date_end": datetime(2025, 1, 6, 11, 0),
            "resource_id": self.resource.id,
            "allocated_percentage": 100.0,
        }
        before = self.Model.new(values).schedule_overlap_count
        saved = self.Model.create(values)
        self.env.invalidate_all()
        self.assertEqual(before, saved.schedule_overlap_count)


    def test_calendar_change(self):
        record = self.Model.create(
            {
                "name": "Calendar change",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 8.0)
        self.assertEqual(record.resource_calendar_id, self.calendar)

        half_calendar = self.env["resource.calendar"].create(
            {
                "name": "Half Day Calendar",
                "tz": "UTC",
                "attendance_ids": [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "name": "Mon AM",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Tue AM",
                            "dayofweek": "1",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Wed AM",
                            "dayofweek": "2",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thu AM",
                            "dayofweek": "3",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Fri AM",
                            "dayofweek": "4",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                ],
            }
        )
        half_resource = self.env["resource.resource"].create(
            {
                "name": "Half Day Resource",
                "calendar_id": half_calendar.id,
                "tz": "UTC",
            }
        )
        record.resource_id = half_resource
        self.assertEqual(record.resource_calendar_id, half_calendar)
        self.assertEqual(record.allocated_hours, 4.0)

    def test_allocated_hours_follow_the_ledger_after_a_replan(self):
        record = self.Model.create(
            {
                "name": "Replanned",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 8.0)
        record.write({"date_end": datetime(2025, 1, 7, 17, 0)})
        self.assertEqual(record.allocated_hours, 16.0)
        self.assertEqual(sum(record.reservation_ids.mapped("allocated_hours")), 16.0)

    def test_an_undated_record_books_no_hours(self):
        record = self.Model.create({"name": "Estimate only", "allocated_hours": 16.0})
        record.write({"resource_id": self.resource.id, "allocated_hours": 12.0})
        self.assertFalse(record.reservation_ids)
        self.assertEqual(record.allocated_hours, 0.0)

    def test_allocated_hours_resets_when_reservations_are_unlinked(self):
        record = self.Model.create(
            {
                "name": "Cleared by unlink",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 8.0)
        record.reservation_ids.unlink()
        record.invalidate_recordset(["allocated_hours"])
        self.assertEqual(record.allocated_hours, 0.0)

    def test_a_record_due_no_reservation_books_no_hours(self):
        with patch.object(
            type(self.Model),
            "_prepare_reservation_vals_list",
            autospec=True,
            return_value=[],
        ):
            record = self.Model.create(
                {
                    "name": "Due no reservation",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 17, 0),
                    "resource_id": self.resource.id,
                }
            )
            record.write({"allocated_hours": 6.0})
            self.assertTrue(record.date_start and record.date_end)
            self.assertFalse(record.reservation_ids)
            self.assertEqual(record.allocated_hours, 0.0)

    def test_allocated_hours_resets_when_dates_are_cleared(self):
        record = self.Model.create(
            {
                "name": "Cleared by unscheduling",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        self.assertEqual(record.allocated_hours, 8.0)
        record.write({"date_start": False, "date_end": False})
        self.assertFalse(record.reservation_ids)
        self.assertEqual(record.allocated_hours, 0.0)

    def test_reactivating_with_new_dates_writes_the_reservation_once(self):
        record = self.Model.create(
            {
                "name": "Reactivated",
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
                "resource_id": self.resource.id,
            }
        )
        record.write({"active": False})
        reservation_id = record.with_context(active_test=False).reservation_ids.id
        self.assertTrue(reservation_id)

        Reservation = type(record.reservation_ids)
        with patch.object(
            Reservation, "write", autospec=True, side_effect=Reservation.write
        ) as write_spy:
            record.write(
                {
                    "active": True,
                    "date_start": datetime(2025, 1, 7, 8, 0),
                    "date_end": datetime(2025, 1, 7, 17, 0),
                }
            )
        self.assertEqual(write_spy.call_count, 1)
        reservation = record.with_context(active_test=False).reservation_ids
        self.assertEqual(reservation.id, reservation_id)
        self.assertEqual(reservation.date_start, datetime(2025, 1, 7, 8, 0))
        self.assertTrue(reservation.active)

    def test_allocated_hours_are_fresh_right_after_create(self):
        records = self.Model.create(
            [
                {
                    "name": f"Batch {i}",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 17, 0),
                    "resource_id": self.resource.id,
                }
                for i in range(3)
            ]
        )
        with self.assertQueryCount(__system__=0):
            self.assertEqual(records.mapped("allocated_hours"), [8.0, 8.0, 8.0])


@tagged("post_install", "-at_install")
class TestSchedulingMixinAllocationBounds(TransactionCase):
    """The mixin rejects an out-of-range allocation share on the consumer.

    ``resource.reservation`` carries the same rule, but the value originates on
    the consumer: without a check here the user got a constraint violation on a
    mirror row they never see, instead of an error on the field they edited.
    A negative share is the dangerous one — the cumulative overlap sweep sums
    these numbers, so it cancels real bookings out of conflict detection.
    """

    def _record(self, **vals):
        return self.env["resource.scheduling.test"].create({"name": "bounds", **vals})

    def test_negative_allocation_rejected(self):
        with self.assertRaises(ValidationError):
            self._record(allocated_percentage=-50.0)

    def test_allocation_above_100_rejected(self):
        with self.assertRaises(ValidationError):
            self._record(allocated_percentage=150.0)

    def test_write_is_guarded_too(self):
        record = self._record(allocated_percentage=100.0)
        with self.assertRaises(ValidationError):
            record.allocated_percentage = -1.0

    def test_boundaries_accepted(self):
        self.assertTrue(self._record(allocated_percentage=0.0))
        self.assertTrue(self._record(allocated_percentage=100.0))


@tagged("post_install", "-at_install")
class TestSchedulingMixinSurplusRelease(TransactionCase):
    """Releasing a surplus reservation must not need the user's own rights.

    ``base.group_user`` holds *read-only* access to ``resource.reservation`` --
    the rows are engine-owned mirrors, written only by the projection. Creating
    one has always gone through ``sudo``; deleting a surplus one did not,
    because the recordset collecting them is built from ``self.browse()`` and
    ``union`` answers in the environment of its left operand, discarding the
    ``sudo`` the rows were fetched with. So an ordinary user who moved a
    booking from one resource to another got an AccessError from a sync that
    was only tidying up after them.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, "surplus_release_user", groups="base.group_user"
        )
        cls.resource_a, cls.resource_b = cls.env["resource.resource"].create(
            [{"name": "Resource A"}, {"name": "Resource B"}]
        )

    def test_moving_a_booking_between_resources_as_a_plain_user(self):
        record = (
            self.env["resource.scheduling.test"]
            .with_user(self.user)
            .create(
                {
                    "name": "surplus",
                    "date_start": datetime(2025, 1, 6, 8, 0),
                    "date_end": datetime(2025, 1, 6, 12, 0),
                    "resource_id": self.resource_a.id,
                }
            )
        )
        record.resource_id = self.resource_b

        reservations = (
            self.env["resource.reservation"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("res_model", "=", "resource.scheduling.test"),
                    ("res_id", "=", record.id),
                ]
            )
        )
        self.assertEqual(
            reservations.resource_id,
            self.resource_b,
            "the booking moved, leaving no claim on the resource it left",
        )


@tagged("post_install", "-at_install")
class TestSchedulingMixinCopy(TransactionCase):
    def test_copy_does_not_duplicate_reservations(self):
        calendar = self.env["resource.calendar"].create({"name": "Cal", "tz": "UTC"})
        resource = self.env["resource.resource"].create(
            {"name": "Machine", "calendar_id": calendar.id, "tz": "UTC"}
        )
        record = self.env["resource.scheduling.test"].create(
            {
                "name": "Original",
                "resource_id": resource.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 12, 0),
            }
        )
        self.assertEqual(len(record.reservation_ids), 1)
        copy = record.copy({"date_start": False, "date_end": False})
        self.assertFalse(
            copy.reservation_ids,
            "a copy with no dates must not inherit the original's bookings",
        )
        self.assertEqual(
            self.env["resource.reservation"].search_count(
                [("resource_id", "=", resource.id)]
            ),
            1,
        )


@tagged("post_install", "-at_install")
class TestSchedulingMixinFollowsTheLedger(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create({"name": "40h", "tz": "UTC"})
        cls.machine = cls.env["resource.resource"].create(
            {
                "name": "Press",
                "type": "material",
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )
        cls.at = datetime(2025, 1, 6, 9, 0)
        cls.until = datetime(2025, 1, 6, 10, 0)

    def test_conflict_count_counts_distinct_foreign_claims(self):
        host = self.env["resource.scheduling.test"].create(
            {
                "name": "host",
                "resource_id": self.machine.id,
                "date_start": self.at,
                "date_end": self.until,
            }
        )
        Reservation = self.env["resource.reservation"]
        Reservation.create(
            {
                "name": "second own claim",
                "res_model": host._name,
                "res_id": host.id,
                "resource_id": self.machine.id,
                "date_start": self.at,
                "date_end": self.until,
            }
        )
        alone = self.env["resource.scheduling.test"].search(
            [("id", "=", host.id), ("schedule_overlap_count", "!=", 0)]
        )
        self.assertFalse(alone, "a host does not conflict with itself")
        foreign = Reservation.create(
            {
                "name": "foreign",
                "resource_id": self.machine.id,
                "date_start": self.at,
                "date_end": self.until,
            }
        )
        host.invalidate_recordset()
        self.assertEqual(host._get_schedule_conflicts_batch()[host.id], foreign)
        self.assertEqual(host.schedule_overlap_count, 1)
        self.assertEqual(
            self.env["resource.scheduling.test"].search(
                [("id", "=", host.id), ("schedule_overlap_count", "!=", 0)]
            ),
            host,
        )

    def test_host_hours_follow_time_off(self):
        host = self.env["resource.scheduling.test"].create(
            {
                "name": "host",
                "resource_id": self.machine.id,
                "date_start": datetime(2025, 1, 6, 8, 0),
                "date_end": datetime(2025, 1, 6, 17, 0),
            }
        )
        self.assertEqual(host.allocated_hours, 8.0)
        self.env["resource.schedule.exception"].create(
            {
                "name": "Maintenance",
                "resource_id": self.machine.id,
                "date_from": datetime(2025, 1, 6, 0, 0),
                "date_to": datetime(2025, 1, 6, 23, 59, 59),
            }
        )
        self.assertEqual(host.reservation_ids.allocated_hours, 0.0)
        self.assertEqual(host.allocated_hours, 0.0)


class TestSchedulingConsumers(ResourceCase):
    def test_consumer_can_filter_its_conflicted_records(self):
        resource = self._resource(name="Consumer conflict")
        model = self.env["resource.scheduling.test"]
        vals = {
            "company_id": self.company.id,
            "resource_id": resource.id,
            "date_start": datetime(2026, 3, 4, 8, 0),
            "date_end": datetime(2026, 3, 4, 12, 0),
        }
        first = model.create({"name": "one", **vals})
        second = model.create({"name": "two", **vals})
        conflicted = model.search([("schedule_overlap_count", "!=", 0)])
        self.assertLessEqual({first.id, second.id}, set(conflicted.ids))

    def test_orphan_reservations_are_garbage_collected(self):
        resource = self._resource(name="Orphan maker")
        record = self.env["resource.scheduling.test"].create(
            {
                "name": "will be deleted behind the ORM's back",
                "company_id": self.company.id,
                "resource_id": resource.id,
                "date_start": datetime(2026, 3, 2, 8, 0),
                "date_end": datetime(2026, 3, 2, 17, 0),
            }
        )
        self.env.flush_all()
        record_id = record.id
        self.env.cr.execute(
            "DELETE FROM resource_scheduling_test WHERE id = %s", (record_id,)
        )
        self.env.invalidate_all()

        reservations = self.env["resource.reservation"].search(
            [("res_model", "=", "resource.scheduling.test"), ("res_id", "=", record_id)]
        )
        self.assertTrue(reservations, "precondition: the orphan survives the delete")

        self.env["resource.reservation"]._gc_orphan_reservations()
        self.assertFalse(reservations.exists())

    def test_gc_keeps_live_and_standalone_reservations(self):
        resource = self._resource(name="Keep me")
        live = self.env["resource.scheduling.test"].create(
            {
                "name": "alive",
                "company_id": self.company.id,
                "resource_id": resource.id,
                "date_start": datetime(2026, 3, 2, 8, 0),
                "date_end": datetime(2026, 3, 2, 17, 0),
            }
        )
        standalone = self.env["resource.reservation"].create(
            {
                "name": "no origin",
                "resource_id": resource.id,
                "date_start": datetime(2026, 3, 9, 8, 0),
                "date_end": datetime(2026, 3, 9, 17, 0),
            }
        )
        self.env.flush_all()
        mirrored = live.reservation_ids
        self.assertTrue(mirrored)

        self.env["resource.reservation"]._gc_orphan_reservations()
        self.assertTrue(mirrored.exists(), "a live consumer keeps its reservations")
        self.assertTrue(
            standalone.exists(), "a booking with no origin is not an orphan"
        )
