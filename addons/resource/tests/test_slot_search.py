from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import Command
from odoo.exceptions import AccessError
from odoo.libs.intervals import Intervals
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.utils import find_available_interval


@tagged("post_install", "-at_install")
class TestSlotSearch(TransactionCase):
    def setUp(self):
        super().setUp()
        self.anchor = datetime(2024, 1, 1, 8, tzinfo=UTC)
        self.records = self.env["resource.calendar.attendance"]
        self.available = Intervals(
            [
                (
                    self.anchor + timedelta(days=day),
                    self.anchor + timedelta(days=day, hours=4),
                    self.records,
                )
                for day in range(3)
            ]
        )
        self.occupied = Intervals()

    def _intervals(self, start, stop):
        window = Intervals([(start, stop, self.records)])
        return self.available & window, self.occupied & window

    def _find(self, duration=timedelta(hours=1), **kwargs):
        return find_available_interval(
            kwargs.pop("anchor", self.anchor),
            duration,
            self._intervals,
            iterations=kwargs.pop("iterations", 3),
            step=kwargs.pop("step", timedelta(days=1)),
            **kwargs,
        )

    def test_forward_duration_spans_calendar_pauses(self):
        self.assertEqual(
            self._find(timedelta(hours=6)),
            (self.anchor, self.anchor + timedelta(days=1, hours=2)),
        )

    def test_backward_duration_spans_calendar_pauses(self):
        self.assertEqual(
            self._find(
                timedelta(hours=6),
                anchor=self.anchor + timedelta(days=1, hours=4),
                forward=False,
            ),
            (
                self.anchor + timedelta(hours=2),
                self.anchor + timedelta(days=1, hours=4),
            ),
        )

    def test_forward_keeps_conflicts_from_previous_windows(self):
        self.occupied = Intervals(
            [
                (
                    self.anchor + timedelta(hours=10),
                    self.anchor + timedelta(hours=11),
                    self.records,
                )
            ]
        )
        self.assertEqual(
            self._find(timedelta(hours=6)),
            (self.anchor + timedelta(days=1), self.anchor + timedelta(days=2, hours=2)),
        )

    def test_backward_keeps_conflicts_from_later_windows(self):
        self.occupied = Intervals(
            [
                (
                    self.anchor + timedelta(days=1, hours=10),
                    self.anchor + timedelta(days=1, hours=11),
                    self.records,
                )
            ]
        )
        self.assertEqual(
            self._find(
                timedelta(hours=6),
                anchor=self.anchor + timedelta(days=2, hours=4),
                forward=False,
            ),
            (
                self.anchor + timedelta(hours=2),
                self.anchor + timedelta(days=1, hours=4),
            ),
        )

    def test_explicit_blocks_reset_the_candidate(self):
        blocked = Intervals(
            [(self.anchor, self.anchor + timedelta(hours=2), self.records)]
        )
        self.assertEqual(
            self._find(blocked=blocked),
            (self.anchor + timedelta(hours=2), self.anchor + timedelta(hours=3)),
        )

    def test_backward_respects_earliest_placement(self):
        self.assertIsNone(
            self._find(
                timedelta(hours=4),
                anchor=self.anchor + timedelta(hours=4),
                forward=False,
                earliest=self.anchor + timedelta(hours=2),
            )
        )

    def test_duration_never_rounds_past_a_working_interval(self):
        self.assertIsNone(self._find(timedelta(hours=4, microseconds=1), iterations=1))

    def test_invalid_search_parameters(self):
        for values in (
            {"duration": timedelta(0)},
            {"step": timedelta(0)},
            {"iterations": 0},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self._find(**values)

    def test_forward_starts_at_a_later_earliest_bound(self):
        earliest = self.anchor + timedelta(days=2)
        self.assertEqual(
            self._find(earliest=earliest), (earliest, earliest + timedelta(hours=1))
        )

    def test_working_duration_uses_elapsed_time_across_dst(self):
        tz = ZoneInfo("Europe/Paris")
        self.anchor = datetime(2024, 3, 31, tzinfo=UTC)
        self.available = Intervals(
            [
                (
                    datetime(2024, 3, 31, 1, tzinfo=tz),
                    datetime(2024, 3, 31, 4, tzinfo=tz),
                    self.records,
                )
            ]
        )
        self.assertIsNone(self._find(timedelta(hours=3), iterations=1))


@tagged("post_install", "-at_install")
class TestSlotIntervals(TransactionCase):
    def setUp(self):
        super().setUp()
        self.start = datetime(2024, 1, 1, 8, tzinfo=UTC)
        self.stop = self.start + timedelta(hours=8)
        self.calendar = self.env["resource.calendar"].create(
            {
                "name": "Exclusive slot calendar",
                "tz": "UTC",
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Monday",
                            "dayofweek": "0",
                            "day_period": "morning",
                            "hour_from": 8,
                            "hour_to": 16,
                        }
                    )
                ],
            }
        )
        self.resource = self.env["resource.resource"].create(
            {
                "name": "Exclusive slot resource",
                "type": "material",
                "calendar_id": self.calendar.id,
            }
        )
        self.claim = self.env["resource.reservation"].create(
            {
                "name": "Private reservation name",
                "resource_id": self.resource.id,
                "date_start": self.start.replace(tzinfo=None),
                "date_end": (self.start + timedelta(hours=2)).replace(tzinfo=None),
                "allocated_percentage": 100,
                "enforcement_mode": "hard",
            }
        )

    def test_inputs_keep_working_time_separate_from_hard_occupancy(self):
        available, occupied = self.resource._get_slot_intervals(self.start, self.stop)
        self.assertEqual([(a, b) for a, b, _ in available], [(self.start, self.stop)])
        self.assertEqual(
            [(a, b) for a, b, _ in occupied],
            [
                (self.start, self.start + timedelta(hours=2)),
            ],
        )
        for _start, _stop, records in occupied:
            self.assertFalse(records)
            self.assertEqual(records._name, "resource.calendar.attendance")

    def test_ignored_claim_bypasses_prefetched_occupancy(self):
        snapshot = self.resource._get_slot_intervals_batch(self.start, self.stop)
        available, occupied = self.resource._get_slot_intervals(
            self.start,
            self.stop,
            reservations_to_ignore=self.claim,
            snapshot=snapshot,
        )
        self.assertTrue(available)
        self.assertFalse(occupied)
        self.assertTrue(snapshot[(self.resource.id, self.calendar.id)][3])

    def test_snapshot_clips_both_inputs_to_requested_bounds(self):
        snapshot = self.resource._get_slot_intervals_batch(self.start, self.stop)
        stop = self.start + timedelta(hours=1)
        available, occupied = self.resource._get_slot_intervals(
            self.start,
            stop,
            snapshot=snapshot,
        )
        self.assertEqual([(a, b) for a, b, _ in available], [(self.start, stop)])
        self.assertEqual([(a, b) for a, b, _ in occupied], [(self.start, stop)])
        self.assertEqual(hash(snapshot), object.__hash__(snapshot))

    def test_no_calendar_is_free_at_any_hour(self):
        self.resource.calendar_id = False
        self.assertEqual(self.resource.calendar_id.schedule_type, "fully_flexible")
        available, occupied = self.resource._get_slot_intervals(self.start, self.stop)
        self.assertEqual(
            sum((b - a).total_seconds() for a, b, _ in available),
            (self.stop - self.start).total_seconds(),
        )
        self.assertTrue(occupied)

    def test_invalid_bounds_rejected_with_and_without_snapshot(self):
        snapshot = self.resource._get_slot_intervals_batch(self.start, self.stop)
        with self.assertRaises(ValueError):
            self.resource._get_slot_intervals(self.start, self.start, snapshot=snapshot)
        with self.assertRaises(ValueError):
            self.resource._get_slot_intervals_batch(self.stop, self.start)

    def test_batch_keeps_resource_occupancy_independent(self):
        other = self.resource.copy({"name": "Independent slot resource"})
        snapshot = (self.resource | other)._get_slot_intervals_batch(
            self.start, self.stop
        )
        self.assertEqual(len(snapshot), 2)
        self.assertTrue(snapshot[(self.resource.id, self.calendar.id)][3])
        self.assertFalse(snapshot[(other.id, self.calendar.id)][3])
        self.assertEqual(
            [(a, b) for a, b, _ in snapshot[(other.id, self.calendar.id)][2]],
            [(self.start, self.stop)],
        )

    def test_snapshot_cannot_bypass_resource_read_access(self):
        reader = new_test_user(
            self.env, login="slot_resource_reader", groups="base.group_user"
        )
        company = self.env["res.company"].create({"name": "Hidden slot company"})
        calendar = self.calendar.copy({"company_id": company.id})
        hidden = self.env["resource.resource"].create(
            {
                "name": "Hidden slot resource",
                "type": "material",
                "company_id": company.id,
                "calendar_id": calendar.id,
            }
        )
        snapshot = hidden._get_slot_intervals_batch(self.start, self.stop)
        resource = hidden.with_user(reader)
        with self.assertRaises(AccessError):
            resource._get_slot_intervals(self.start, self.stop, snapshot=snapshot)
        with self.assertRaises(AccessError):
            resource._get_slot_intervals_batch(self.start, self.stop)

    def test_dst_fold_bounds_are_compared_in_utc(self):
        zone = ZoneInfo("Europe/Paris")
        start = datetime(2024, 10, 27, 2, 30, tzinfo=zone, fold=0)
        stop = datetime(2024, 10, 27, 2, 30, tzinfo=zone, fold=1)
        snapshot = self.resource._get_slot_intervals_batch(start, stop)
        window = snapshot[(self.resource.id, self.calendar.id)]
        self.assertEqual(window[0], datetime(2024, 10, 27, 0, 30, tzinfo=UTC))
        self.assertEqual(window[1], datetime(2024, 10, 27, 1, 30, tzinfo=UTC))
        available, occupied = self.resource._get_slot_intervals(
            start, stop, snapshot=snapshot
        )
        self.assertFalse(available)
        self.assertFalse(occupied)
