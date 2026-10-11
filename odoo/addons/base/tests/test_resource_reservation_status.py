from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestReservationStatus(TransactionCase):
    def setUp(self):
        super().setUp()
        self.resource = self.env["resource.resource"].create(
            {
                "name": "Shared station",
                "type": "material",
                "company_id": False,
                "calendar_id": False,
                "capacity": 3,
            }
        )
        self.at = datetime(2026, 1, 1, 10)

    def _claim(self, start=9, end=11, **values):
        return self.env["resource.reservation"].create(
            {
                "name": "Private booking",
                "resource_id": self.resource.id,
                "date_start": datetime(2026, 1, 1, start),
                "date_end": datetime(2026, 1, 1, end),
                "allocated_percentage": 25,
                **values,
            }
        )

    def test_half_open_bounds_and_partial_occupancy(self):
        self._claim()
        self.assertTrue(
            self.resource._get_reservation_status(datetime(2026, 1, 1, 9))[
                self.resource.id
            ]["is_reserved"]
        )
        self.assertFalse(
            self.resource._get_reservation_status(datetime(2026, 1, 1, 11))[
                self.resource.id
            ]["is_reserved"]
        )

    def test_inactive_zero_and_ended_claims_do_not_occupy(self):
        self._claim(active=False)
        self._claim(allocated_percentage=0)
        self._claim(start=8, end=10)
        self.assertEqual(
            self.resource._get_reservation_status(self.at)[self.resource.id],
            {"is_reserved": False, "next_reservation_start": None},
        )

    def test_current_and_next_claims_are_independent(self):
        self._claim()
        self._claim(start=14, end=15)
        self._claim(start=12, end=13)
        status = self.resource._get_reservation_status(self.at)[self.resource.id]
        self.assertTrue(status["is_reserved"])
        self.assertEqual(status["next_reservation_start"], datetime(2026, 1, 1, 12))

    def test_unscheduled_claims_do_not_occupy(self):
        self._claim(date_start=False)
        self._claim(date_end=False)
        self._claim(start=12, end=12)
        self.assertEqual(
            self.resource._get_reservation_status(self.at)[self.resource.id],
            {"is_reserved": False, "next_reservation_start": None},
        )

    def test_aware_lookup_uses_utc(self):
        self._claim()
        instant = datetime(2026, 1, 1, 19, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertEqual(
            self.resource._get_reservation_status(instant),
            self.resource._get_reservation_status(self.at),
        )

    def test_occupancy_window_excludes_adjacent_and_unscheduled_claims(self):
        self._claim(start=9, end=10)
        inside = self._claim(start=10, end=11)
        self._claim(start=11, end=12)
        self._claim(date_start=False)
        self._claim(date_end=False)
        self._claim(allocated_percentage=0)
        self._claim(active=False)
        self._claim(
            date_start=datetime(2026, 1, 1, 10, 30),
            date_end=datetime(2026, 1, 1, 10, 30),
        )
        reservations = self.env["resource.reservation"]
        domain = reservations._get_domain_occupancy(
            self.resource, since=self.at, until=datetime(2026, 1, 1, 11)
        )
        self.assertEqual(reservations.search(domain), inside)

    def test_occupancy_window_normalizes_aware_bounds(self):
        claim = self._claim()
        reservations = self.env["resource.reservation"]
        domain = reservations._get_domain_occupancy(
            self.resource,
            since=datetime(2026, 1, 1, 19, tzinfo=ZoneInfo("Asia/Tokyo")),
            until=datetime(2026, 1, 1, 20, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual(reservations.search(domain), claim)

    def test_empty_occupancy_windows_and_resource_sets(self):
        self._claim()
        reservations = self.env["resource.reservation"]
        for stop in (self.at, datetime(2026, 1, 1, 9)):
            with self.subTest(stop=stop):
                domain = reservations._get_domain_occupancy(
                    self.resource, since=self.at, until=stop
                )
                self.assertFalse(reservations.search(domain))
        self.assertFalse(
            reservations.search(
                reservations._get_domain_occupancy(self.env["resource.resource"])
            )
        )

    def test_zero_allocation_does_not_remove_work_time(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "UTC working calendar", "tz": "UTC"}
        )
        self.resource.calendar_id = calendar
        start = datetime(2026, 1, 1, 8, tzinfo=UTC)
        stop = datetime(2026, 1, 1, 17, tzinfo=UTC)
        before = calendar._work_intervals_batch(start, stop, self.resource)[
            self.resource.id
        ]
        self._claim(allocated_percentage=0, enforcement_mode="hard")
        after = calendar._work_intervals_batch(start, stop, self.resource)[
            self.resource.id
        ]
        self.assertTrue(before)
        self.assertEqual([(a, b) for a, b, _ in after], [(a, b) for a, b, _ in before])

    def test_booking_load_ignores_empty_claims(self):
        claim = self._claim()
        self._claim(allocated_percentage=0)
        self._claim(active=False)
        self._claim(start=12, end=12)
        self._claim(date_start=False)
        self._claim(date_end=False)
        loads = self.env["resource.reservation"]._get_booking_load_batch(
            self.resource, datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 15)
        )
        self.assertEqual(
            loads[self.resource.id], [(claim.date_start, claim.date_end, 25)]
        )

    def test_empty_hard_claim_can_be_created_in_an_overbooked_window(self):
        self._claim(allocated_percentage=150)
        empty = self._claim(allocated_percentage=0, enforcement_mode="hard")
        self.assertTrue(empty.exists())

    def test_existing_empty_hard_claim_does_not_enforce_a_ceiling(self):
        self._claim(allocated_percentage=0, enforcement_mode="hard")
        occupied = self._claim(allocated_percentage=150)
        self.assertEqual(occupied.allocated_percentage, 150)

    def test_batch_includes_resources_without_claims(self):
        self._claim()
        other = self.resource.copy({"name": "Idle station"})
        status = (self.resource | other)._get_reservation_status(self.at)
        self.assertTrue(status[self.resource.id]["is_reserved"])
        self.assertFalse(status[other.id]["is_reserved"])
        self.assertEqual(
            self.env["resource.resource"]._get_reservation_status(self.at), {}
        )

    def test_hidden_claims_contribute_only_occupancy_facts(self):
        company = self.env["res.company"].create({"name": "Other operator"})
        claim = self._claim(company_id=company.id, resource_calendar_id=False)
        reader = new_test_user(
            self.env, login="reservation_status_reader", groups="base.group_user"
        )
        self.assertFalse(
            self.env["resource.reservation"]
            .with_user(reader)
            .search([("id", "=", claim.id)])
        )
        status = self.resource.with_user(reader)._get_reservation_status(self.at)[
            self.resource.id
        ]
        self.assertEqual(status, {"is_reserved": True, "next_reservation_start": None})

    def test_summary_requires_resource_visibility(self):
        company = self.env["res.company"].create({"name": "Private station company"})
        self.resource.company_id = company
        reader = new_test_user(
            self.env, login="private_station_reader", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            self.resource.with_user(reader)._get_reservation_status(self.at)
