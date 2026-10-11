from datetime import date, datetime, timedelta

from odoo import exceptions
from odoo.tests import tagged

from odoo.addons.event.tests.common import EventCase


class TestEventSlotsCommon(EventCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.reference_now = datetime(2025, 4, 15, 10, 0, 0)
        cls.reference_beg = datetime(2025, 4, 21, 6, 30, 0)
        cls.reference_end = datetime(2025, 8, 21, 17, 45, 0)

        with cls.mock_datetime_and_now(cls, cls.reference_now):
            cls.test_event = cls.env["event.event"].create(
                {
                    "date_begin": cls.reference_beg,
                    "date_end": cls.reference_end,
                    "date_tz": "Europe/Brussels",
                    "event_ticket_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Classic",
                                "seats_limited": False,
                                "seats_max": 0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Better",
                                "seats_limited": True,
                                "seats_max": 3,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "VIP",
                                "seats_limited": True,
                                "seats_max": 1,
                            },
                        ),
                    ],
                    "name": "Test Event",
                    "seats_limited": True,
                    "seats_max": 5,
                    "event_slot_ids": [
                        (
                            0,
                            0,
                            {
                                "date": date(2025, 4, 21),
                                "end_hour": 12,
                                "start_hour": 9,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "date": date(2025, 4, 21),
                                "end_hour": 16,
                                "start_hour": 13,
                            },
                        ),
                    ],
                    "user_id": cls.user_eventuser.id,
                }
            )

            first_slot = cls.test_event.event_slot_ids.filtered(
                lambda s: s.start_hour == 9
            )
            second_slot = cls.test_event.event_slot_ids.filtered(
                lambda s: s.start_hour == 13
            )
            first_ticket = cls.test_event.event_ticket_ids.filtered(
                lambda t: t.name == "Classic"
            )
            second_ticket = cls.test_event.event_ticket_ids.filtered(
                lambda t: t.name == "Better"
            )

            cls.test_reg_slot_1 = cls._create_registrations_for_slot_and_ticket(
                cls.test_event, first_slot, first_ticket, 3
            )
            cls.test_reg_slot_2 = cls._create_registrations_for_slot_and_ticket(
                cls.test_event, second_slot, second_ticket, 1
            )


@tagged("event_slot", "event_registration")
class TestEventSlotRegistration(TestEventSlotsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_event_no_slot = cls.env["event.event"].create(
            {
                "date_begin": cls.reference_beg,
                "date_end": cls.reference_end,
                "date_tz": "Europe/Brussels",
                "name": "Test Event No Slot",
            }
        )
        cls.test_reg_no_slot = cls.env["event.registration"].create(
            {
                "event_id": cls.test_event_no_slot.id,
                "name": "Test Registration No Slot",
            }
        )

    def test_search_event_begin_date(self):
        for search_from_date, expected in [
            (
                self.reference_beg,
                self.test_reg_no_slot + self.test_reg_slot_1 + self.test_reg_slot_2,
            ),
            (
                self.reference_beg + timedelta(minutes=30),
                self.test_reg_slot_1 + self.test_reg_slot_2,
            ),
            (self.reference_beg + timedelta(hours=1), self.test_reg_slot_2),
        ]:
            self.assertEqual(
                self.env["event.registration"].search(
                    [
                        (
                            "event_id",
                            "in",
                            [self.test_event_no_slot.id, self.test_event.id],
                        ),
                        ("event_begin_date", ">=", search_from_date),
                    ]
                ),
                expected,
            )

    def test_search_event_end_date(self):
        for search_to_date, expected in [
            (
                self.reference_end,
                self.test_reg_no_slot + self.test_reg_slot_1 + self.test_reg_slot_2,
            ),
            (
                self.reference_beg + timedelta(hours=12),
                self.test_reg_slot_1 + self.test_reg_slot_2,
            ),
            (self.reference_beg + timedelta(hours=6), self.test_reg_slot_1),
        ]:
            self.assertEqual(
                self.env["event.registration"].search(
                    [
                        (
                            "event_id",
                            "in",
                            [self.test_event_no_slot.id, self.test_event.id],
                        ),
                        ("event_end_date", "<=", search_to_date),
                    ]
                ),
                expected,
            )


@tagged("event_slot", "event_seats")
class TestEventSlotSeats(TestEventSlotsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_event_slot_noticket = cls.test_event.copy({"event_ticket_ids": False})

        first_slot = cls.test_event_slot_noticket.event_slot_ids.filtered(
            lambda s: s.start_hour == 9
        )
        second_slot = cls.test_event_slot_noticket.event_slot_ids.filtered(
            lambda s: s.start_hour == 13
        )

        with cls.mock_datetime_and_now(cls, cls.reference_now):
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, first_slot, False, 1, state="open"
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, first_slot, False, 2, state="done"
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, first_slot, False, 1, active=False
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, second_slot, False, 1
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, second_slot, False, 2, active=False
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, second_slot, False, 1, state="cancel"
            )
            cls._create_registrations_for_slot_and_ticket(
                cls.test_event_slot_noticket, second_slot, False, 1, state="draft"
            )

    def test_assert_initial_values(self):
        test_event = self.test_event.with_user(self.user_eventregistrationdesk)
        first_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 9)
        second_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 13)
        self.assertTrue(first_slot)
        self.assertTrue(second_slot)
        self.assertEqual(first_slot.seats_available, 2)
        self.assertEqual(first_slot.seats_reserved, 3)
        self.assertEqual(second_slot.seats_available, 4)
        self.assertEqual(second_slot.seats_reserved, 1)

        test_event_nt = self.test_event_slot_noticket.with_user(
            self.user_eventregistrationdesk
        )
        first_slot = test_event_nt.event_slot_ids.filtered(lambda s: s.start_hour == 9)
        second_slot = test_event_nt.event_slot_ids.filtered(
            lambda s: s.start_hour == 13
        )
        self.assertTrue(first_slot)
        self.assertTrue(second_slot)
        self.assertEqual(first_slot.seats_available, 2)
        self.assertEqual(first_slot.seats_reserved, 1)
        self.assertEqual(second_slot.seats_available, 4)
        self.assertEqual(second_slot.seats_reserved, 1)

    def test_seats_slots_notickets(self):
        test_event = self.test_event_slot_noticket.with_user(
            self.user_eventregistrationdesk
        )
        first_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 9)
        second_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 13)

        Registration = self.env["event.registration"].with_user(
            self.user_eventregistrationdesk
        )

        res = test_event._get_seats_availability(
            [(first_slot, False), (second_slot, False)]
        )
        self.assertEqual(res, [first_slot.seats_available, second_slot.seats_available])

        for create_input, should_crash in [
            (((first_slot, 2), (second_slot, 2)), False),
            (((first_slot, 3),), True),
            (((second_slot, 5),), True),
        ]:
            with self.subTest(create_input=create_input, should_crash=should_crash):
                create_values = []
                for slot, count in create_input:
                    create_values += [
                        {
                            "email": f"{slot.display_name}.{idx}@test.example.com",
                            "event_id": test_event.id,
                            "event_slot_id": slot.id,
                            "name": f"{slot.display_name} {idx}",
                        }
                        for idx in range(count)
                    ]
                if should_crash:
                    with self.assertRaises(exceptions.ValidationError):
                        new = Registration.create(create_values)
                else:
                    new = Registration.create(create_values)
                    self.assertEqual(
                        len(new), sum(count for _slot, count in create_input)
                    )
                    new.with_user(self.user_eventmanager).unlink()

        for check_input, should_crash in [
            (((first_slot, False, 2), (second_slot, False, 4)), False),
            (((first_slot, False, 3),), True),
            (((second_slot, False, 5),), True),
        ]:
            with self.subTest(check_input=check_input, should_crash=should_crash):
                if should_crash:
                    with self.assertRaises(exceptions.ValidationError):
                        test_event._check_seats_availability(check_input)
                else:
                    test_event._check_seats_availability(check_input)

        all_slot2 = test_event.with_context(
            active_test=False
        ).registration_ids.filtered(lambda r: r.event_slot_id == second_slot)
        self.assertEqual(len(all_slot2), 5, "Test setup data: 3 active, 2 inactive")
        all_slot2.active = True
        self.assertEqual(second_slot.seats_available, 2)
        self.assertEqual(second_slot.seats_reserved, 3)

        with self.assertRaises(exceptions.ValidationError):
            all_slot2.event_slot_id = first_slot.id

    def test_seats_slots_tickets(self):
        test_event = self.test_event.with_user(self.user_eventregistrationdesk)
        first_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 9)
        second_slot = test_event.event_slot_ids.filtered(lambda s: s.start_hour == 13)
        first_ticket = test_event.event_ticket_ids.filtered(
            lambda t: t.name == "Classic"
        )
        second_ticket = test_event.event_ticket_ids.filtered(
            lambda t: t.name == "Better"
        )
        third_ticket = test_event.event_ticket_ids.filtered(lambda t: t.name == "VIP")

        Registration = self.env["event.registration"].with_user(
            self.user_eventregistrationdesk
        )

        res = test_event._get_seats_availability(
            [
                (first_slot, first_ticket),
                (first_slot, second_ticket),
                (first_slot, third_ticket),
                (second_slot, first_ticket),
                (second_slot, second_ticket),
                (second_slot, third_ticket),
            ]
        )
        self.assertEqual(res, [2, 2, 1, 4, 2, 1])

        for create_input, should_crash in [
            (((first_slot, second_ticket, 2),), False),
            (((first_slot, first_ticket, 5),), True),
            (((second_slot, third_ticket, 2),), True),
        ]:
            with self.subTest(create_input=create_input, should_crash=should_crash):
                create_values = []
                for slot, ticket, count in create_input:
                    create_values += [
                        {
                            "email": f"{slot.display_name}.{ticket.name}.{idx}@test.example.com",
                            "event_id": test_event.id,
                            "event_slot_id": slot.id,
                            "event_ticket_id": ticket.id,
                            "name": f"{slot.display_name} {ticket.name} {idx}",
                        }
                        for idx in range(count)
                    ]
                if should_crash:
                    with self.assertRaises(exceptions.ValidationError):
                        new = Registration.create(create_values)
                else:
                    new = Registration.create(create_values)
                    self.assertEqual(
                        len(new), sum(count for _slot, _ticket, count in create_input)
                    )
                    new.with_user(self.user_eventmanager).unlink()

        with self.assertRaises(exceptions.ValidationError):
            test_event.with_user(self.user_eventmanager).write(
                {
                    "registration_ids": [
                        (
                            0,
                            0,
                            {
                                "event_slot_id": second_slot.id,
                                "event_ticket_id": third_ticket.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "event_slot_id": second_slot.id,
                                "event_ticket_id": third_ticket.id,
                            },
                        ),
                    ],
                }
            )
        test_event.with_user(self.user_eventmanager).write(
            {
                "registration_ids": [
                    (
                        0,
                        0,
                        {
                            "event_slot_id": second_slot.id,
                            "event_ticket_id": third_ticket.id,
                            "active": False,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "event_slot_id": second_slot.id,
                            "event_ticket_id": third_ticket.id,
                        },
                    ),
                ],
            }
        )
        archived_vip = test_event.with_context(
            active_test=False
        ).registration_ids.filtered(
            lambda r: (
                r.event_slot_id == second_slot
                and r.event_ticket_id == third_ticket
                and not r.active
            )
        )
        self.assertTrue(archived_vip)
        with self.assertRaises(exceptions.ValidationError):
            archived_vip.active = True
