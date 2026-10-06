from freezegun import freeze_time

from odoo import http
from odoo.exceptions import UserError
from odoo.tests import users
from odoo.tools import mute_logger

from odoo.addons.appointment_account_payment.tests.common import (
    AppointmentAccountPaymentCommon,
)


class WebsiteAppointmentSaleTest(AppointmentAccountPaymentCommon):
    def test_invoice_cancellation_route_cannot_detach_cart_booking(self):
        booking = self.env["calendar.booking"].create(
            {
                "appointment_type_id": self.appointment_users_payment.id,
                "product_id": self.appointment_users_payment.product_id.id,
                "partner_id": self.apt_manager.partner_id.id,
                "staff_user_id": self.staff_user_bxls.id,
                "start": self.start_slot,
                "stop": self.stop_slot,
                "asked_capacity": 1,
            }
        )
        order = self.env["sale.order"].create({"partner_id": booking.partner_id.id})
        order._cart_add(
            product_id=booking.product_id.id,
            quantity=1,
            calendar_booking_id=booking.id,
        )
        line = booking.order_line_id
        self.assertTrue(line)
        self.authenticate("apt_manager", "apt_manager")
        response = self.url_open(
            f"/calendar_booking/{booking.booking_token}/cancel",
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(booking.exists())
        self.assertTrue(line.exists())

        order._cart_update_line_quantity(line.id, 0)
        self.assertFalse(booking.exists())
        self.assertFalse(line.exists())

    def test_a_free_booking_reaches_the_cart_of_a_shop_hiding_free_products(self):
        product = self.appointment_users_payment.product_id
        product.list_price = 0
        website = self.env["website"].create(
            {"name": "Free products hidden", "prevent_zero_price_sale": True}
        )
        booking = self.env["calendar.booking"].create(
            {
                "appointment_type_id": self.appointment_users_payment.id,
                "product_id": product.id,
                "partner_id": self.apt_manager.partner_id.id,
                "staff_user_id": self.staff_user_bxls.id,
                "start": self.start_slot,
                "stop": self.stop_slot,
                "asked_capacity": 1,
            }
        )
        order = self.env["sale.order"].create(
            {"partner_id": booking.partner_id.id, "website_id": website.id}
        )
        order._cart_add(
            product_id=product.id, quantity=1, calendar_booking_id=booking.id
        )
        self.assertEqual(booking.order_line_id.price_unit, 0)
        shop_order = self.env["sale.order"].create(
            {"partner_id": booking.partner_id.id, "website_id": website.id}
        )
        with self.assertRaises(UserError):
            shop_order._cart_add(product_id=product.id, quantity=1)

    @mute_logger("odoo.db.cursor")
    @users("apt_manager")
    def test_booking_to_event_collisions_resources(self):
        apt_manage_capacity = self.appointment_resources_payment
        apt_multiple_bookings = apt_manage_capacity.copy({"manage_capacity": False})
        self.resource_1.unlink()

        for appointment_type in apt_multiple_bookings + apt_manage_capacity:
            with self.subTest(
                appointment_type=appointment_type,
                capacity_mode=appointment_type.manage_capacity,
            ):
                total_availability = 2 if appointment_type.manage_capacity else 1
                start = self.start_slot
                stop = self.stop_slot

                resources_remaining_capacity = (
                    appointment_type._get_resources_remaining_capacity(
                        appointment_type.resource_ids, start, stop
                    )
                )
                self.assertEqual(
                    resources_remaining_capacity["total_remaining_capacity"],
                    total_availability,
                )

                booking_values = {
                    "appointment_type_id": appointment_type.id,
                    "asked_capacity": total_availability,
                    "duration": 1.0,
                    "partner_id": self.apt_manager.partner_id.id,
                    "product_id": appointment_type.product_id.id,
                    "start": start,
                    "stop": stop,
                }
                calendar_booking_line_values = {
                    "resource_id": self.resource_2.id,
                    "capacity_reserved": total_availability,
                    "capacity_used": total_availability,
                }

                calendar_booking_1 = self.env["calendar.booking"].create(booking_values)
                calendar_booking_line_values["calendar_booking_id"] = (
                    calendar_booking_1.id
                )
                self.env["calendar.booking.line"].create(calendar_booking_line_values)
                sale_order_1 = (
                    self.env["sale.order"]
                    .sudo()
                    .create({"partner_id": calendar_booking_1.partner_id.id})
                )
                cart_values = sale_order_1._cart_add(
                    product_id=appointment_type.product_id.id,
                    quantity=1,
                    calendar_booking_id=calendar_booking_1.id,
                )
                self.assertEqual(cart_values["quantity"], 1)
                sale_order_line_1 = sale_order_1.line_ids.filtered_domain(
                    [("id", "=", cart_values["line_id"])]
                )
                self.assertTrue(sale_order_line_1)
                self.assertFalse(sale_order_line_1.calendar_event_id)

                resources_remaining_capacity = (
                    appointment_type._get_resources_remaining_capacity(
                        appointment_type.resource_ids, start, stop
                    )
                )
                self.assertEqual(
                    resources_remaining_capacity["total_remaining_capacity"],
                    total_availability,
                )

                calendar_booking_2 = self.env["calendar.booking"].create(booking_values)
                calendar_booking_line_values["calendar_booking_id"] = (
                    calendar_booking_2.id
                )
                self.env["calendar.booking.line"].create(calendar_booking_line_values)
                sale_order_2 = (
                    self.env["sale.order"]
                    .sudo()
                    .create({"partner_id": calendar_booking_2.partner_id.id})
                )

                self.assertTrue(
                    (
                        sale_order_1.line_ids.calendar_booking_ids | calendar_booking_2
                    )._filter_unavailable_bookings()
                )
                self.assertFalse(
                    (
                        sale_order_2.line_ids.calendar_booking_ids | calendar_booking_2
                    )._filter_unavailable_bookings()
                )
                cart_values = sale_order_2._cart_add(
                    product_id=appointment_type.product_id.id,
                    quantity=1,
                    calendar_booking_id=calendar_booking_2.id,
                )
                self.assertEqual(cart_values["quantity"], 1)
                sale_order_line_2 = sale_order_2.line_ids.filtered_domain(
                    [("id", "=", cart_values["line_id"])]
                )
                self.assertTrue(sale_order_line_2)
                self.assertFalse(sale_order_line_2.calendar_event_id)

                sale_order_1._action_confirm()
                sale_order_2._action_confirm()
                self.assertTrue(calendar_booking_1.calendar_event_id)
                self.assertEqual(sale_order_1.calendar_event_count, 1)
                self.assertTrue(
                    calendar_booking_2.not_available
                    and not calendar_booking_2.calendar_event_id
                )
                self.assertEqual(sale_order_2.calendar_event_count, 0)

                resources_remaining_capacity = (
                    appointment_type._get_resources_remaining_capacity(
                        appointment_type.resource_ids, start, stop
                    )
                )
                self.assertEqual(
                    resources_remaining_capacity["total_remaining_capacity"], 0
                )

                calendar_booking_1.calendar_event_id.unlink()

    @freeze_time("2022-02-13 20:00:00")
    @mute_logger("odoo.db.cursor")
    @users("apt_manager")
    def test_booking_to_event_collisions_users(self):
        apt_multiple_bookings = self.appointment_users_payment
        apt_manage_capacity = apt_multiple_bookings.copy(
            {"manage_capacity": True, "user_capacity": 5}
        )
        start = self.start_slot
        stop = self.stop_slot

        for appointment_type in apt_multiple_bookings + apt_manage_capacity:
            with self.subTest(
                appointment_type=appointment_type,
                capacity_mode=appointment_type.manage_capacity,
            ):
                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 1)
                total_availability = 5 if appointment_type.manage_capacity else 1

                users_remaining_capacity = (
                    appointment_type._get_users_remaining_capacity(
                        appointment_type.staff_user_ids, start, stop
                    )
                )
                self.assertEqual(
                    users_remaining_capacity["total_remaining_capacity"],
                    total_availability,
                )

                booking_values = {
                    "appointment_type_id": appointment_type.id,
                    "duration": 1.0,
                    "partner_id": self.apt_manager.partner_id.id,
                    "product_id": appointment_type.product_id.id,
                    "staff_user_id": self.staff_user_bxls.id,
                    "start": start,
                    "stop": stop,
                }
                calendar_booking_line_values = {
                    "capacity_reserved": total_availability,
                    "capacity_used": total_availability,
                }
                calendar_booking_1 = self.env["calendar.booking"].create(booking_values)
                calendar_booking_line_values["calendar_booking_id"] = (
                    calendar_booking_1.id
                )
                self.env["calendar.booking.line"].create(calendar_booking_line_values)
                sale_order_1 = (
                    self.env["sale.order"]
                    .sudo()
                    .create({"partner_id": calendar_booking_1.partner_id.id})
                )
                cart_values = sale_order_1._cart_add(
                    product_id=appointment_type.product_id.id,
                    quantity=1,
                    calendar_booking_id=calendar_booking_1.id,
                )
                self.assertEqual(cart_values["quantity"], 1)
                sale_order_line_1 = sale_order_1.line_ids.filtered_domain(
                    [("id", "=", cart_values["line_id"])]
                )
                self.assertTrue(sale_order_line_1)
                self.assertFalse(sale_order_line_1.calendar_event_id)

                remaining_capacity = appointment_type._get_users_remaining_capacity(
                    appointment_type.staff_user_ids, start, stop
                )
                self.assertEqual(
                    remaining_capacity["total_remaining_capacity"], total_availability
                )

                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 1)

                calendar_booking_2 = self.env["calendar.booking"].create(booking_values)
                calendar_booking_line_values["calendar_booking_id"] = (
                    calendar_booking_2.id
                )
                self.env["calendar.booking.line"].create(calendar_booking_line_values)
                sale_order_2 = (
                    self.env["sale.order"]
                    .sudo()
                    .create({"partner_id": calendar_booking_2.partner_id.id})
                )

                self.assertTrue(
                    (
                        sale_order_1.line_ids.calendar_booking_ids | calendar_booking_2
                    )._filter_unavailable_bookings()
                )
                self.assertFalse(
                    (sale_order_2.line_ids.calendar_booking_ids | calendar_booking_2)
                    .with_context(debug=True)
                    ._filter_unavailable_bookings()
                )
                cart_values = sale_order_2._cart_add(
                    product_id=appointment_type.product_id.id,
                    quantity=1,
                    calendar_booking_id=calendar_booking_2.id,
                )
                self.assertEqual(cart_values["quantity"], 1)
                sale_order_line_2 = sale_order_2.line_ids.filtered_domain(
                    [("id", "=", cart_values["line_id"])]
                )
                self.assertTrue(sale_order_line_2)
                self.assertFalse(sale_order_line_2.calendar_event_id)

                sale_order_1._action_confirm()
                sale_order_2._action_confirm()
                self.assertTrue(calendar_booking_1.calendar_event_id)
                self.assertEqual(sale_order_1.calendar_event_count, 1)
                self.assertTrue(
                    calendar_booking_2.not_available
                    and not calendar_booking_2.calendar_event_id
                )
                self.assertEqual(sale_order_2.calendar_event_count, 0)

                slots = appointment_type._get_appointment_slots("UTC")
                slots_list = self._filter_appointment_slots(slots)
                self.assertEqual(len(slots_list), 0)

                users_remaining_capacity = (
                    appointment_type._get_users_remaining_capacity(
                        appointment_type.staff_user_ids, start, stop
                    )
                )
                self.assertEqual(
                    users_remaining_capacity["total_remaining_capacity"], 0
                )

                calendar_booking_1.calendar_event_id.unlink()

    @mute_logger("odoo.db.cursor")
    @users("apt_manager")
    def test_booking_to_event_on_so_confirmation_resource(self):
        appointment_type = self.appointment_resources_payment
        asked_capacity = 3
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
        calendar_booking_line_values = {
            "resource_id": self.resource_1.id,
            "calendar_booking_id": calendar_booking.id,
            "capacity_reserved": asked_capacity,
            "capacity_used": asked_capacity,
        }
        calendar_booking_line = self.env["calendar.booking.line"].create(
            calendar_booking_line_values
        )

        resources_remaining_capacity = (
            appointment_type._get_resources_remaining_capacity(
                appointment_type.resource_ids, start, stop
            )
        )
        self.assertEqual(resources_remaining_capacity["total_remaining_capacity"], 5)

        sale_order = (
            self.env["sale.order"]
            .sudo()
            .create({"partner_id": calendar_booking.partner_id.id})
        )
        self.assertFalse(calendar_booking._filter_unavailable_bookings())
        cart_values = sale_order._cart_add(
            product_id=appointment_type.product_id.id,
            quantity=1,
            calendar_booking_id=calendar_booking.id,
        )
        self.assertEqual(cart_values["quantity"], 1)
        sale_order_line = sale_order.line_ids.filtered(
            lambda line, line_id=cart_values["line_id"]: line.id == line_id
        )
        self.assertTrue(sale_order_line)
        self.assertEqual(sale_order_line.calendar_booking_ids, calendar_booking)
        self.assertFalse(sale_order_line.calendar_event_id)

        sale_order._action_confirm()
        event = sale_order_line.calendar_event_id
        self.assertTrue(event)
        self.assertEqual(event, calendar_booking.calendar_event_id)

        resources_remaining_capacity = (
            appointment_type._get_resources_remaining_capacity(
                appointment_type.resource_ids, start, stop
            )
        )
        self.assertEqual(resources_remaining_capacity["total_remaining_capacity"], 2)

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

        booking_line = event.booking_line_ids
        self.assertEqual(len(booking_line), 1)
        self.assertTrue(booking_line.active)
        self.assertEqual(
            booking_line.resource_id,
            calendar_booking_line.resource_id,
        )
        self.assertEqual(booking_line.appointment_type_id, appointment_type)
        self.assertEqual(
            booking_line.capacity_reserved, calendar_booking_line.capacity_reserved
        )
        self.assertEqual(
            booking_line.capacity_used, calendar_booking_line.capacity_used
        )
        self.assertEqual(booking_line.event_start, calendar_booking.start)
        self.assertEqual(booking_line.event_stop, calendar_booking.stop)

    @freeze_time("2022-02-13 20:00:00")
    @mute_logger("odoo.db.cursor")
    @users("apt_manager")
    def test_booking_to_event_on_so_confirmation_users(self):
        appointment_type = self.appointment_users_payment
        start = self.start_slot
        stop = self.stop_slot

        slots = appointment_type._get_appointment_slots("UTC")
        slots_list = self._filter_appointment_slots(slots)
        self.assertEqual(len(slots_list), 1)

        booking_values = {
            "appointment_type_id": appointment_type.id,
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

        sale_order = (
            self.env["sale.order"]
            .sudo()
            .create({"partner_id": calendar_booking.partner_id.id})
        )
        self.assertFalse(calendar_booking._filter_unavailable_bookings())
        cart_values = sale_order._cart_add(
            product_id=appointment_type.product_id.id,
            quantity=1,
            calendar_booking_id=calendar_booking.id,
        )
        self.assertEqual(cart_values["quantity"], 1)
        sale_order_line = sale_order.line_ids.filtered(
            lambda line, line_id=cart_values["line_id"]: line.id == line_id
        )
        self.assertTrue(sale_order_line)
        self.assertEqual(sale_order_line.calendar_booking_ids, calendar_booking)
        self.assertFalse(sale_order_line.calendar_event_id)

        slots = appointment_type._get_appointment_slots("UTC")
        slots_list = self._filter_appointment_slots(slots)
        self.assertEqual(len(slots_list), 1)

        sale_order._action_confirm()
        event = sale_order_line.calendar_event_id
        self.assertTrue(event)
        self.assertEqual(event, calendar_booking.calendar_event_id)

        slots = appointment_type._get_appointment_slots("UTC")
        slots_list = self._filter_appointment_slots(slots)
        self.assertEqual(
            len(slots_list),
            0,
            "Confirming the SO with SOL linked to a booking creates an event booking the slot",
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
            calendar_booking.partner_id | calendar_booking.staff_user_id.partner_id,
        )
        self.assertEqual(event.start, calendar_booking.start)
        self.assertEqual(event.stop, calendar_booking.stop)
        self.assertTrue(
            all(attendee.state == "accepted" for attendee in event.attendee_ids)
        )
