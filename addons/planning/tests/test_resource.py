from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import TestCommonPlanning


@tagged("post_install", "-at_install")
class TestPlanningResource(TestCommonPlanning):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpEmployees()

        cls.res_willywaller = cls.env["resource.resource"].create(
            {"name": "Willy Waller 2006", "type": "material"}
        )

    def test_resource_material(self):
        slot_a = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
            }
        )
        self.assertEqual(
            slot_a.state,
            "2_published",
            "Shift with resource type material should be published by default",
        )

        slot_b = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_janice.id,
                "start_datetime": datetime(2019, 6, 6, 13, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 17, 0, 0),
            }
        )
        slot_b.resource_id = self.res_willywaller.id
        self.assertEqual(
            slot_a.state,
            "2_published",
            "Changing resource with resource type material should make shift published",
        )

        slot_b.action_unpublish()
        self.assertEqual(
            slot_b.state,
            "2_published",
            "Even after unpublish, Material resource shift should always be published",
        )

    def test_resource_conflicts(self):
        slot_a = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "allocated_hours": 4,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
            }
        )
        self.assertEqual(slot_a.overlap_slot_count, 0)

        slot_b = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "allocated_hours": 4,
                "start_datetime": datetime(2019, 6, 6, 13, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 17, 0, 0),
            }
        )
        self.assertEqual(slot_a.overlap_slot_count, 0)
        self.assertEqual(slot_b.overlap_slot_count, 0)

        slot_b.start_datetime = datetime(2019, 6, 6, 11, 0, 0)
        self.assertEqual(slot_b.overlap_slot_count, 1, "Should have a conflict")
        self.assertIn(
            slot_a.id,
            slot_b.conflicting_slot_ids.ids,
            "slot_a should conflict with slot_b",
        )

        slot_a.resource_id = self.resource_bert
        self.assertEqual(slot_a.overlap_slot_count, 0)

    def test_cumulative_over_allocation_is_a_conflict(self):
        """Three 50% shifts on one resource are 150% of it.

        No *pair* of them exceeds 100, so the pairwise
        `S1.allocated_percentage + S2.allocated_percentage > 100` this used to
        run reported nothing. Conflicts now come from the reservation ledger's
        cumulative sweep, which measures the total claim at each instant.
        """
        window = {
            "resource_id": self.res_willywaller.id,
            "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
            "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
        }
        first, second = self.env["planning.slot"].create(
            [
                dict(window, allocated_percentage=50),
                dict(window, allocated_percentage=50),
            ]
        )
        self.env.invalidate_all()
        self.assertEqual(
            first.overlap_slot_count,
            0,
            "50 + 50 is exactly the resource, not more than it",
        )

        third = self.env["planning.slot"].create(dict(window, allocated_percentage=50))
        self.env.invalidate_all()
        for slot in (first, second, third):
            self.assertEqual(
                slot.overlap_slot_count,
                2,
                "each of the three is over-allocated against the other two",
            )
        self.assertEqual(
            set(first.conflicting_slot_ids.ids),
            {second.id, third.id},
            "the conflict list names the peers, never the slot itself",
        )

    def test_conflicts_reach_across_models(self):
        """A shift sees a clash with any claim on its resource, not only shifts.

        The reservation ledger is shared, so a resource booked by something
        outside planning is visible here -- which is the point of projecting
        into it. `overlap_slot_count` stays shift-to-shift because its m2m is
        typed to `planning.slot`; the mixin's `schedule_overlap_count` is what
        counts everything.
        """
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
            }
        )
        self.env["resource.reservation"].create(
            {
                "name": "Booked elsewhere",
                "resource_id": self.res_willywaller.id,
                "date_start": datetime(2019, 6, 6, 9, 0, 0),
                "date_end": datetime(2019, 6, 6, 11, 0, 0),
                "allocated_percentage": 100.0,
            }
        )
        self.env.invalidate_all()
        self.assertEqual(
            slot.overlap_slot_count,
            0,
            "no *shift* conflicts with it, so the shift-typed list stays empty",
        )
        self.assertGreater(
            slot.schedule_overlap_count,
            0,
            "but the resource is genuinely double-booked, and that is visible",
        )

    def test_resource_material_publication_warning(self):
        slot_a = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
            }
        )
        self.assertFalse(slot_a.publication_warning)
        self.assertEqual(
            slot_a.state, "2_published", "Shift should be published by default"
        )

        slot_a.start_datetime = datetime(2019, 6, 6, 11, 0, 0)
        self.assertFalse(
            slot_a.publication_warning,
            "Shift does not have publication warning for material type resource",
        )

        slot_a.resource_id = self.resource_janice
        self.assertTrue(
            slot_a.publication_warning,
            "Shift will display the publication warning for human type resource",
        )

        slot_a.resource_id = self.res_willywaller
        self.assertFalse(
            slot_a.publication_warning,
            "Shift should not show publication warning for changing resoure from human type to material type",
        )

    def test_resource_human_publication_warning(self):
        slot_a = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_janice.id,
                "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                "end_datetime": datetime(2019, 6, 6, 12, 0, 0),
            }
        )
        self.assertFalse(slot_a.publication_warning)
        self.assertEqual(slot_a.state, "1_draft")

        slot_a.action_send()
        self.assertFalse(
            slot_a.publication_warning,
            "Shift should not have publication warning when user publish the shift",
        )
        self.assertEqual(slot_a.state, "2_published")

        slot_a.start_datetime = datetime(2019, 6, 6, 11, 0, 0)
        self.assertTrue(
            slot_a.publication_warning,
            "Shift should have publication warning when user change date of shift",
        )

        slot_a.resource_id = False
        self.assertFalse(slot_a.publication_warning)
        self.assertEqual(slot_a.state, "2_published")

        slot_a.resource_id = False
        self.assertFalse(slot_a.publication_warning)

        slot_a.resource_id = self.resource_bert
        self.assertTrue(slot_a.publication_warning)

    @freeze_time("2021-07-15")
    def test_resource_default_hours(self):
        full_calendar = self.env["resource.calendar"].create(
            {
                "name": "Classic 40h/week",
                "tz": "UTC",
                "hours_per_day": 8.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday Morning",
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
                            "name": "Monday Lunch",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Monday Afternoon",
                            "dayofweek": "0",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Tuesday Morning",
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
                            "name": "Tuesday Lunch",
                            "dayofweek": "1",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Tuesday Afternoon",
                            "dayofweek": "1",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Wednesday Morning",
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
                            "name": "Wednesday Lunch",
                            "dayofweek": "2",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Wednesday Afternoon",
                            "dayofweek": "2",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Morning",
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
                            "name": "Thursday Lunch",
                            "dayofweek": "3",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Afternoon",
                            "dayofweek": "3",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Friday Morning",
                            "dayofweek": "4",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Friday Lunch",
                            "dayofweek": "4",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Friday Afternoon",
                            "dayofweek": "4",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )
        self.resource_bert.calendar_id = full_calendar
        self.resource_bert.tz = "UTC"

        half_calendar = self.env["resource.calendar"].create(
            {
                "name": "Classic 20h/week",
                "tz": "UTC",
                "hours_per_day": 4.0,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Monday Morning",
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
                            "name": "Tuesday Morning",
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
                            "name": "Wednesday Morning",
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
                            "name": "Thursday Morning",
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
                            "name": "Friday Morning",
                            "dayofweek": "4",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                ],
            }
        )
        self.res_willywaller.calendar_id = half_calendar
        self.res_willywaller.tz = "UTC"

        self.env.user.tz = "UTC"

        bert_data = (
            self.env["planning.slot"]
            .with_context(default_resource_id=self.resource_bert.id)
            .default_get(["resource_id", "start_datetime", "end_datetime"])
        )
        self.assertDictEqual(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": datetime(2021, 7, 15, 8, 0, 0),
                "end_datetime": datetime(2021, 7, 15, 17, 0, 0),
            },
            bert_data,
            "The dault start/date should adapt to the resource calendar",
        )

        willy_data = (
            self.env["planning.slot"]
            .with_context(default_resource_id=self.res_willywaller.id)
            .default_get(["resource_id", "start_datetime", "end_datetime"])
        )
        self.assertDictEqual(
            {
                "resource_id": self.res_willywaller.id,
                "start_datetime": datetime(2021, 7, 15, 8, 0, 0),
                "end_datetime": datetime(2021, 7, 15, 12, 0, 0),
            },
            willy_data,
            "The dault start/date should adapt to the resource calendar",
        )

    def test_partial_booking_does_not_erase_planned_effort(self):
        self.res_willywaller.tz = "UTC"
        start, stop = datetime(2019, 6, 6, 8), datetime(2019, 6, 6, 12)
        self.env["resource.reservation"].create(
            {
                "name": "Half booked elsewhere",
                "resource_id": self.res_willywaller.id,
                "date_start": start,
                "date_end": stop,
                "allocated_percentage": 50,
                "enforcement_mode": "hard",
            }
        )
        shift = self.env["planning.slot"].create(
            {
                "resource_id": self.res_willywaller.id,
                "start_datetime": start,
                "end_datetime": stop,
                "allocated_percentage": 50,
            }
        )
        self.assertAlmostEqual(shift.allocated_hours, 2)
        self.assertAlmostEqual(shift.reservation_ids.allocated_hours, 2)
        self.assertEqual(shift.reservation_ids.peak_booking_percentage, 100)

    def test_resource_ceiling_constrains_manual_shifts(self):
        self.res_willywaller.write(
            {"enforce_booking_limit": True, "booking_limit_percentage": 150}
        )
        values = {
            "resource_id": self.res_willywaller.id,
            "start_datetime": datetime(2030, 1, 7, 8),
            "end_datetime": datetime(2030, 1, 7, 12),
            "allocated_percentage": 75,
        }
        first = self.env["planning.slot"].create(values)
        self.env["planning.slot"].create(values)
        self.assertEqual(first.reservation_ids.booking_state, "over")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["planning.slot"].create(values)
        first.unlink()
        self.env["planning.slot"].create(values)


@tagged("post_install", "-at_install")
class TestPlanningColors(TransactionCase):
    def test_palette_and_open_shift_alpha(self):
        expected = (
            "#008784",
            "#EE4B39",
            "#F29648",
            "#F4C609",
            "#55B7EA",
            "#71405B",
            "#E86869",
            "#008784",
            "#267283",
            "#BF1255",
            "#2BAF73",
            "#8754B0",
        )
        role = self.env["resource.role"].create({"name": "Color contract"})
        for index, color in enumerate(expected):
            role.color = index
            self.assertEqual(role._get_color_from_code(False), color)
            self.assertEqual(role._get_color_from_code(True), color + "80")
        for index in (-1, 12):
            role.color = index
            with self.assertRaises(KeyError):
                role._get_color_from_code(False)

    def test_lightening_preserves_opaque_email_colors(self):
        role = self.env["resource.role"].create({"name": "Email color", "color": 1})
        for opened in (False, True):
            for factor, expected in (
                (-1, "#ee4b39"),
                (0, "#ee4b39"),
                (0.2, "#f16f61"),
                (1, "#ffffff"),
                (2, "#ffffff"),
            ):
                self.assertEqual(role._get_light_color(factor, opened), expected)
