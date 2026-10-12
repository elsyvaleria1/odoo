from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, http
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.appointment_account_payment.tests.common import (
    AppointmentAccountPaymentCommon,
)


@tagged("post_install", "-at_install")
class AppointmentAccountPaymentTest(AppointmentAccountPaymentCommon):
    def test_copied_booking_gets_a_distinct_access_token(self):
        booking = self.env["calendar.booking"].create(
            {
                "appointment_type_id": self.appointment_users_payment.id,
                "product_id": self.appointment_users_payment.product_id.id,
                "start": self.start_slot,
                "stop": self.stop_slot,
            }
        )
        duplicate = booking.copy()
        self.assertTrue(duplicate.booking_token)
        self.assertNotEqual(duplicate.booking_token, booking.booking_token)

    def test_booking_retry_clears_unavailability_and_is_idempotent(self):
        values = {
            "appointment_type_id": self.appointment_resources_payment.id,
            "product_id": self.appointment_resources_payment.product_id.id,
            "partner_id": self.apt_manager.partner_id.id,
            "asked_capacity": 3,
            "start": self.start_slot,
            "stop": self.stop_slot,
            "booking_line_ids": [
                Command.create(
                    {
                        "resource_id": self.resource_1.id,
                        "capacity_reserved": 3,
                        "capacity_used": 3,
                    }
                )
            ],
        }
        blocker, booking = self.env["calendar.booking"].create([values, values])
        blocker._create_event_from_paid_booking()
        self.assertTrue(blocker.calendar_event_id)
        booking._create_event_from_paid_booking()
        self.assertFalse(booking.calendar_event_id)
        self.assertTrue(booking.not_available)

        blocker.calendar_event_id.unlink()
        booking._create_event_from_paid_booking()
        event = booking.calendar_event_id
        self.assertTrue(event)
        self.assertFalse(booking.not_available)
        booking._create_event_from_paid_booking()
        self.assertEqual(booking.calendar_event_id, event)
        self.assertEqual(booking.appointment_type_id.meeting_ids, event)

    @mute_logger("odoo.db.cursor")
    @users("apt_manager")
    def test_booking_to_event_on_invoice_paid_resource(self):
        appointment_type = self.appointment_resources_payment
        asked_capacity = 5
        start = self.start_slot
        stop = self.stop_slot

        resources_remaining_capacity = (
            appointment_type._get_resources_remaining_capacity(
                appointment_type.resource_ids, start, stop
            )
        )
        self.assertEqual(resources_remaining_capacity["total_remaining_capacity"], 5)

        booking_values = {
            "appointment_type_id": appointment_type.id,
            "asked_capacity": asked_capacity,
            "duration": 1.0,
            "partner_id": self.apt_manager.partner_id.id,
            "product_id": appointment_type.product_id.id,
            "start": start,
            "stop": stop,
        }
        calendar_booking = self.env["calendar.booking"].create(booking_values)
        calendar_booking_lines_values = {}
        for resource in appointment_type.resource_ids:
            resource_remaining_capacity = resources_remaining_capacity.get(resource)
            new_capacity_reserved = min(
                resource_remaining_capacity, asked_capacity, resource.capacity
            )
            asked_capacity -= new_capacity_reserved
            calendar_booking_lines_values[resource.id] = {
                "resource_id": resource.id,
                "calendar_booking_id": calendar_booking.id,
                "capacity_reserved": new_capacity_reserved,
                "capacity_used": new_capacity_reserved
                if not resource.booking_exclusive and appointment_type.manage_capacity
                else resource.capacity,
            }
        self.env["calendar.booking.line"].create(
            list(calendar_booking_lines_values.values())
        )

        resources_remaining_capacity = (
            appointment_type._get_resources_remaining_capacity(
                appointment_type.resource_ids, start, stop
            )
        )
        self.assertEqual(resources_remaining_capacity["total_remaining_capacity"], 5)

        invoice = calendar_booking.sudo()._create_booking_invoices()
        self.assertEqual(calendar_booking.account_move_id, invoice)
        self.assertFalse(invoice.calendar_booking_ids.calendar_event_id)

        invoice._post()
        event = invoice.calendar_booking_ids.calendar_event_id
        self.assertEqual(len(event), 1)
        self.assertTrue(invoice.calendar_booking_ids.calendar_event_id)
        resources_remaining_capacity = (
            appointment_type._get_resources_remaining_capacity(
                appointment_type.resource_ids, start, stop
            )
        )
        self.assertEqual(resources_remaining_capacity["total_remaining_capacity"], 0)

        self.assertEqual(
            invoice.invoice_line_ids.quantity, calendar_booking.asked_capacity
        )

        self.assertTrue(event.active)
        self.assertEqual(event, calendar_booking.calendar_event_id)
        self.assertEqual(
            event.appointment_type_id, calendar_booking.appointment_type_id
        )
        self.assertEqual(event.total_capacity_reserved, calendar_booking.asked_capacity)
        self.assertEqual(event.total_capacity_used, calendar_booking.asked_capacity)
        self.assertEqual(event.duration, calendar_booking.duration)
        self.assertEqual(event.partner_ids, calendar_booking.partner_id)
        self.assertEqual(event.start, calendar_booking.start)
        self.assertEqual(event.stop, calendar_booking.stop)
        self.assertTrue(
            all(attendee.state == "accepted" for attendee in event.attendee_ids)
        )

        booking_line_1 = event.booking_line_ids.filtered(
            lambda line: line.resource_id == self.resource_1
        )
        booking_line_2 = event.booking_line_ids.filtered(
            lambda line: line.resource_id == self.resource_2
        )
        self.assertEqual(len(booking_line_1 + booking_line_2), 2)
        calendar_booking_lines_by_resource = calendar_booking.booking_line_ids.grouped(
            "resource_id"
        )
        for booking_line in booking_line_1 | booking_line_2:
            calendar_booking_line = calendar_booking_lines_by_resource.get(
                booking_line.resource_id, calendar_booking.booking_line_ids.browse()
            )
            self.assertTrue(calendar_booking_line)
            self.assertTrue(booking_line.active)
            self.assertEqual(
                booking_line.capacity_reserved, calendar_booking_line.capacity_reserved
            )
            self.assertEqual(
                booking_line.capacity_used, calendar_booking_line.capacity_used
            )
            self.assertEqual(booking_line.event_start, calendar_booking.start)
            self.assertEqual(booking_line.event_stop, calendar_booking.stop)

    @mute_logger("odoo.db.cursor")
    @freeze_time("2022-02-13 20:00:00")
    @users("apt_manager")
    def test_booking_to_event_on_invoice_paid_users(self):
        appointment_type = self.appointment_users_payment
        for manage_capacity in (True, False):
            with self.subTest(
                manage_capacity=manage_capacity, capacity_mode=manage_capacity
            ):
                start = self.start_slot
                stop = self.stop_slot

                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 1)

                booking_values = {
                    "appointment_type_id": appointment_type.id,
                    "asked_capacity": 3 if manage_capacity else 1,
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "appointment_user_id": self.staff_user_bxls.id,
                                "capacity_reserved": 1,
                                "capacity_used": 1,
                            },
                        )
                    ],
                    "duration": 1.0,
                    "partner_id": self.apt_manager.partner_id.id,
                    "product_id": appointment_type.product_id.id,
                    "staff_user_id": self.staff_user_bxls.id,
                    "start": start,
                    "stop": stop,
                }
                calendar_booking = self.env["calendar.booking"].create(booking_values)

                invoice = calendar_booking.sudo()._create_booking_invoices()
                self.assertEqual(calendar_booking.account_move_id, invoice)
                self.assertFalse(invoice.calendar_booking_ids.calendar_event_id)

                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 1)

                invoice._post()
                event = invoice.calendar_booking_ids.calendar_event_id
                self.assertEqual(len(event), 1)
                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 0)

                self.assertEqual(
                    invoice.invoice_line_ids.quantity, calendar_booking.asked_capacity
                )

                self.assertTrue(event.active)
                self.assertEqual(event, calendar_booking.calendar_event_id)
                self.assertEqual(
                    event.appointment_type_id, calendar_booking.appointment_type_id
                )
                self.assertEqual(event.duration, calendar_booking.duration)
                self.assertEqual(event.user_id, calendar_booking.staff_user_id)
                self.assertEqual(
                    event.partner_ids,
                    calendar_booking.partner_id
                    | calendar_booking.staff_user_id.partner_id,
                )
                self.assertEqual(event.start, calendar_booking.start)
                self.assertEqual(event.stop, calendar_booking.stop)
                self.assertTrue(
                    all(attendee.state == "accepted" for attendee in event.attendee_ids)
                )

                booking_line, calendar_booking_line = (
                    event.booking_line_ids,
                    calendar_booking.booking_line_ids,
                )
                self.assertEqual(len(booking_line), 1)
                self.assertTrue(booking_line.active)
                self.assertEqual(
                    booking_line.capacity_reserved,
                    calendar_booking_line.capacity_reserved,
                )
                self.assertEqual(
                    booking_line.capacity_used, calendar_booking_line.capacity_used
                )
                self.assertEqual(booking_line.event_start, calendar_booking.start)
                self.assertEqual(booking_line.event_stop, calendar_booking.stop)

                calendar_booking.calendar_event_id.unlink()
                calendar_booking.unlink()

    def test_booking_unlink(self):
        appointment_type = self.appointment_users_payment
        appointment_question = self.env["survey.question"].create(
            {
                "appointment_type_ids": [(6, 0, appointment_type.ids)],
                "title": "How are you ?",
                "question_type": "char_box",
            }
        )
        appointment_answer_input_values = {
            "question_id": appointment_question.id,
            "value_char_box": "I am Good",
            "answer_type": "char_box",
        }
        booking_values = {
            "appointment_type_id": appointment_type.id,
            "appointment_response_ids": [
                Command.create(
                    {
                        "appointment_type_id": appointment_type.id,
                        "predefined_question_ids": [
                            Command.set(appointment_question.ids)
                        ],
                        "user_input_line_ids": [
                            Command.create(appointment_answer_input_values)
                        ],
                    }
                )
            ],
            "duration": 1.0,
            "partner_id": self.apt_manager.partner_id.id,
            "product_id": appointment_type.product_id.id,
            "staff_user_id": self.staff_user_bxls.id,
            "start": self.start_slot,
            "stop": self.stop_slot,
        }
        calendar_booking = self.env["calendar.booking"].create(booking_values)
        self.assertFalse(calendar_booking.calendar_event_id)
        answer_inputs = calendar_booking.appointment_answer_input_ids
        self.assertEqual(len(answer_inputs), 1)

        calendar_booking.unlink()
        self.assertFalse(answer_inputs.exists())

        calendar_booking = self.env["calendar.booking"].create(booking_values)
        answer_inputs = calendar_booking.appointment_answer_input_ids
        calendar_booking._create_event_from_paid_booking()
        self.assertTrue(answer_inputs.calendar_event_id)

        calendar_booking.unlink()
        self.assertTrue(answer_inputs.exists())

    @users("apt_manager")
    def test_contiguous_bookings_availability(self):
        booking_values = {
            "appointment_type_id": self.appointment_users_payment.id,
            "booking_line_ids": [
                (
                    0,
                    0,
                    {
                        "appointment_user_id": self.staff_user_bxls.id,
                        "capacity_reserved": 1,
                        "capacity_used": 1,
                    },
                )
            ],
            "duration": 1.0,
            "partner_id": self.apt_manager.partner_id.id,
            "product_id": self.appointment_users_payment.product_id.id,
            "staff_user_id": self.staff_user_bxls.id,
        }
        calendar_bookings = self.env["calendar.booking"].create(
            [
                {"start": self.start_slot, "stop": self.stop_slot, **booking_values},
                {
                    "start": self.stop_slot,
                    "stop": self.stop_slot + relativedelta(hours=1),
                    **booking_values,
                },
            ]
        )
        self.assertFalse(calendar_bookings._filter_unavailable_bookings())
        calendar_bookings._create_event_from_paid_booking()
        self.assertEqual(len(calendar_bookings.calendar_event_id), 2)

    def test_gc_calendar_booking(self):
        max_creation_dt = self.reference_now - relativedelta(months=6)
        max_stop_dt = self.reference_now - relativedelta(months=2)

        with patch.object(
            self.env.cr, "now", lambda: max_creation_dt - relativedelta(months=1)
        ):
            booking_1, booking_2 = self.env["calendar.booking"].create(
                [
                    {
                        "start": max_stop_dt + relativedelta(hours=1),
                        "stop": max_stop_dt + relativedelta(hours=2),
                        "appointment_type_id": self.appointment_users_payment.id,
                        "product_id": self.appointment_users_payment.product_id.id,
                    },
                    {
                        "start": max_stop_dt - relativedelta(hours=2),
                        "stop": max_stop_dt - relativedelta(hours=1),
                        "appointment_type_id": self.appointment_users_payment.id,
                        "product_id": self.appointment_users_payment.product_id.id,
                    },
                ]
            )
        with patch.object(self.env.cr, "now", lambda: self.reference_now):
            booking_3, booking_4 = self.env["calendar.booking"].create(
                [
                    {
                        "start": max_stop_dt + relativedelta(hours=1),
                        "stop": max_stop_dt + relativedelta(hours=2),
                        "appointment_type_id": self.appointment_users_payment.id,
                        "product_id": self.appointment_users_payment.product_id.id,
                    },
                    {
                        "start": max_stop_dt - relativedelta(hours=2),
                        "stop": max_stop_dt - relativedelta(hours=1),
                        "appointment_type_id": self.appointment_users_payment.id,
                        "product_id": self.appointment_users_payment.product_id.id,
                    },
                ]
            )

        with freeze_time(self.reference_now):
            self.env["calendar.booking"]._gc_calendar_booking()

        self.assertFalse(booking_1.exists())
        self.assertFalse(booking_2.exists())
        self.assertTrue(booking_3.exists())
        self.assertFalse(booking_4.exists())

    @freeze_time("2022-02-13")
    @users("apt_manager")
    def test_no_manage_capacity_paid_resource(self):
        self.assertFalse(self.appointment_resources_payment.meeting_ids)
        self.appointment_resources_payment.write(
            {
                "manage_capacity": False,
                "max_bookings": 1,
            }
        )
        phone_question = self.appointment_resources_payment._get_main_phone_question()
        self.assertTrue(phone_question)

        self.authenticate(self.env.user.login, self.env.user.login)
        appointment_data = {
            "asked_capacity": "1",
            "available_resource_ids": [self.resource_1.id],
            "csrf_token": http.Request.csrf_token(self),
            "datetime_str": "2022-02-14 14:00:00",
            "duration_str": "1.0",
            "email": "test@test.example.com",
            "name": "Online Meeting",
            f"question_{phone_question.id}": "2025550999",
        }

        url = f"/appointment/{self.appointment_resources_payment.id}/submit"
        res = self.url_open(url, data=appointment_data)
        self.assertEqual(res.status_code, 200, "Response should = OK")

        self.assertFalse(self.appointment_resources_payment.meeting_ids)
        booking = self.env["calendar.booking"].search(
            [("appointment_type_id", "=", self.appointment_resources_payment.id)]
        )
        self.assertEqual(len(booking.booking_line_ids), 1)
        self.assertEqual(booking.booking_line_ids.capacity_reserved, 1)
        self.assertEqual(booking.booking_line_ids.capacity_used, 1)
        self.assertFalse(booking._filter_unavailable_bookings())

    def test_response_cannot_be_detached_from_its_only_booking(self):
        from odoo.exceptions import ValidationError

        booking = self.env["calendar.booking"].create(
            {
                "appointment_type_id": self.appointment_users_payment.id,
                "product_id": self.appointment_users_payment.product_id.id,
                "partner_id": self.apt_manager.partner_id.id,
                "start": self.start_slot,
                "stop": self.stop_slot,
            }
        )
        response = self.env["survey.user_input"].create(
            {
                "appointment_type_id": booking.appointment_type_id.id,
                "calendar_booking_id": booking.id,
            }
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            response.calendar_booking_id = False
