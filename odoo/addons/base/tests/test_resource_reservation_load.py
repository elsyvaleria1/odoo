from datetime import UTC, datetime, timedelta

from odoo import fields
from odoo.tests import TransactionCase


class TestReservationLoad(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reservation = cls.env["resource.reservation"]
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "40h UTC", "tz": "UTC"}
        )
        cls.at = datetime(2026, 10, 5, 9, 0)

    def _resource(self, **vals):
        return self.env["resource.resource"].create(
            {"name": "R", "calendar_id": self.calendar.id, "tz": "UTC", **vals}
        )

    def _claim(self, resource, hours=2, at=None, **vals):
        at = at or self.at
        return self.Reservation.create(
            {
                "name": vals.pop("name", "claim"),
                "resource_id": resource.id,
                "date_start": at,
                "date_end": at + timedelta(hours=hours),
                **vals,
            }
        )

    def _monday(self):
        return datetime(2026, 10, 5, tzinfo=UTC), datetime(2026, 10, 6, tzinfo=UTC)

    def _sync_projection(self, record, vals_list, existing=None):
        return self.Reservation._sync_projection_batch([(record, vals_list, existing)])

    def test_enforced_booking_stays_working_time(self):
        resource = self._resource()
        self._claim(resource, hours=4, allocated_percentage=10, enforcement_mode="hard")
        start, stop = self._monday()

        def hours(**kwargs):
            intervals = self.calendar._work_intervals_batch(
                start, stop, resource, **kwargs
            )[resource.id]
            return sum((b - a).total_seconds() / 3600 for a, b, _ in intervals)

        self.assertEqual(hours(), 8.0, "booked time is still worked")
        self.assertEqual(hours(exclude_bookings=True), 5.0, "but it is not free")
        booked = datetime(2026, 10, 5, 10, tzinfo=UTC)

        def unavailable_at(instant, **kwargs):
            return any(
                begin <= instant < end
                for begin, end in resource._get_unavailable_intervals(
                    start, stop, **kwargs
                )[resource.id]
            )

        self.assertTrue(unavailable_at(booked))
        self.assertFalse(unavailable_at(booked, exclude_bookings=False))

    def test_allocated_hours_follow_time_off(self):
        resource = self._resource()
        claim = self._claim(resource, hours=8)
        self.assertEqual(claim.allocated_hours, 7.0)
        self.env["resource.schedule.exception"].create(
            {
                "name": "Sick",
                "resource_id": resource.id,
                "date_from": datetime(2026, 10, 5, 0, 0),
                "date_to": datetime(2026, 10, 6),
            }
        )
        self.assertEqual(claim.allocated_hours, 0.0)

    def test_allocated_hours_follow_a_schedule_closure(self):
        resource = self._resource()
        claim = self._claim(resource, hours=8)
        closure = self.env["resource.schedule.exception"].create(
            {
                "name": "Closed",
                "calendar_id": self.calendar.id,
                "date_from": datetime(2026, 10, 5, 0, 0),
                "date_to": datetime(2026, 10, 6),
            }
        )
        self.assertEqual(claim.allocated_hours, 0.0)
        closure.unlink()
        self.assertEqual(claim.allocated_hours, 7.0)

    def test_allocated_hours_follow_the_resource_zone(self):
        resource = self._resource()
        future = fields.Datetime.now().replace(
            hour=9, minute=0, second=0, microsecond=0
        ) + timedelta(days=7 - fields.Datetime.now().weekday())
        claim = self._claim(resource, hours=8, at=future)
        self.assertEqual(claim.allocated_hours, 7.0)
        resource.tz = "Asia/Tokyo"
        self.assertEqual(claim.allocated_hours, 0.0)

    def test_allocated_hours_follow_the_schedule(self):
        resource = self._resource()
        future = fields.Datetime.now().replace(
            hour=9, minute=0, second=0, microsecond=0
        ) + timedelta(days=7 - fields.Datetime.now().weekday())
        claim = self._claim(resource, hours=8, at=future)
        self.assertEqual(claim.allocated_hours, 7.0)
        monday = self.calendar.attendance_ids.filtered(
            lambda line: line.dayofweek == "0" and line.day_period == "afternoon"
        )
        monday.hour_to = 15
        self.assertEqual(claim.allocated_hours, 5.0)

    def test_zero_percent_claim_conflicts_with_nothing(self):
        machine = self._resource(type="material")
        first = self._claim(machine, allocated_percentage=80)
        second = self._claim(machine, allocated_percentage=80)
        zero = self._claim(machine, allocated_percentage=0)
        self.assertEqual(first.schedule_overlap_count, 1)
        self.assertEqual(second.schedule_overlap_count, 1)
        self.assertEqual(zero.schedule_overlap_count, 0)
        self.assertFalse(
            self.Reservation._get_prospective_conflicts(
                [
                    {
                        "resource_id": machine.id,
                        "date_start": self.at,
                        "date_end": self.at + timedelta(hours=1),
                        "allocated_percentage": 0,
                    }
                ]
            )
        )

    def test_draft_counts_its_own_load(self):
        machine = self._resource(type="material")
        saved = self._claim(machine, allocated_percentage=80)
        draft = self.Reservation.new(
            {
                "name": "draft",
                "resource_id": machine.id,
                "date_start": self.at,
                "date_end": self.at + timedelta(hours=2),
                "allocated_percentage": 80,
            }
        )
        self.assertEqual(draft.peak_booking_percentage, 160)
        self.assertEqual(draft.booking_state, "exceeded")
        edited = self.Reservation.new(
            {"date_start": self.at + timedelta(hours=4)}, origin=saved
        )
        edited.date_end = self.at + timedelta(hours=6)
        self.assertEqual(edited.peak_booking_percentage, 80)

    def test_enabling_the_ceiling_ignores_history(self):
        machine = self._resource(type="material")
        past = datetime(2020, 1, 6, 9, 0)
        self._claim(machine, at=past, name="x")
        self._claim(machine, at=past, name="y")
        machine.enforce_booking_limit = True
        self.assertTrue(machine.enforce_booking_limit)

    def test_free_window_ignores_claims_on_nothing(self):
        machine = self._resource(type="material")
        self._claim(machine, allocated_percentage=0)
        self.assertEqual(machine._find_free_window(self.at, 1)[0], self.at)
        self._claim(machine, hours=2)
        self.assertEqual(
            machine._find_free_window(self.at, 1)[0], self.at + timedelta(hours=2)
        )

    def test_cleanup_keeps_claims_of_view_models(self):
        view_model = next(
            name
            for name, model in self.env.registry.items()
            if not model._auto and not model._abstract and not model._transient
        )
        claim = self._claim(
            self._resource(type="material"), res_model=view_model, res_id=1
        )
        orphan = self._claim(
            self._resource(type="material"),
            res_model="resource.resource",
            res_id=0,
        )
        self.Reservation._gc_orphan_reservations()
        self.assertTrue(claim.exists())
        self.assertFalse(orphan.exists())

    def test_sync_reaches_a_valid_state_through_no_invalid_one(self):
        machine = self._resource(type="material", enforce_booking_limit=True)
        source = self.env["res.partner"].create({"name": "Source"})
        later = self.at + timedelta(hours=1)
        claim = {"resource_id": machine.id, "enforcement_mode": "hard"}
        self._sync_projection(
            source,
            [
                {**claim, "name": "a", "date_start": self.at, "date_end": later},
                {
                    **claim,
                    "name": "b",
                    "date_start": later,
                    "date_end": later + timedelta(hours=1),
                },
            ],
        )
        kept = self.Reservation.search([("res_id", "=", source.id)]).filtered(
            lambda row: row.name == "b"
        )
        result = self._sync_projection(
            source,
            [
                {
                    **claim,
                    "name": "b",
                    "date_start": later,
                    "date_end": later + timedelta(hours=1),
                }
            ],
        )
        self.assertEqual(result, kept, "the matching row is kept, not rewritten")
