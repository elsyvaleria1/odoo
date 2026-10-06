from datetime import datetime

from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBookingFeeProducts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.booking_product = cls.env["product.product"].create(
            {
                "name": "Booking Fee",
                "type": "service",
                "sale_ok": True,
                "service_tracking": "no",
                "list_price": 5.0,
            }
        )
        cls.appointment_type = cls.env["appointment.type"].create(
            {
                "name": "Paid Consultation",
                "has_payment_step": True,
                "product_id": cls.booking_product.id,
            }
        )

    def test_is_booking_fee_requires_paid_appointment_type(self):
        self.assertTrue(self.booking_product.is_booking_fee)

        plain_service = self.env["product.product"].create(
            {"name": "Plain Service", "type": "service", "sale_ok": True}
        )
        self.assertFalse(plain_service.is_booking_fee)

        consumable = self.env["product.product"].create(
            {"name": "Goods", "type": "consu", "sale_ok": True}
        )
        self.assertFalse(consumable.is_booking_fee)

    def test_booking_fee_image_is_public(self):
        as_public = self.booking_product.with_user(self.env.ref("base.public_user"))
        self.assertTrue(as_public._can_return_content("image_128"))
        self.assertFalse(as_public._can_return_content("standard_price"))

    def test_booking_fee_placeholder_image(self):
        self.assertEqual(
            self.booking_product._get_product_placeholder_filename(),
            "appointment_account_payment/static/src/img/booking_product.png",
        )
        other = self.env["product.product"].create({"name": "Other", "type": "consu"})
        self.assertNotEqual(
            other._get_product_placeholder_filename(),
            "appointment_account_payment/static/src/img/booking_product.png",
        )

    def test_event_sale_order_count_and_action(self):
        partner = self.env["res.partner"].create({"name": "Attendee"})
        event = self.env["calendar.event"].create(
            {
                "name": "Paid Meeting",
                "start": datetime(2026, 7, 24, 10),
                "stop": datetime(2026, 7, 24, 11),
            }
        )
        empty_event = self.env["calendar.event"].create(
            {
                "name": "Free Meeting",
                "start": datetime(2026, 7, 24, 12),
                "stop": datetime(2026, 7, 24, 13),
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.booking_product.id,
                            "calendar_event_id": event.id,
                        }
                    )
                ],
            }
        )
        self.assertEqual(event.sale_order_count, 1)
        self.assertEqual(empty_event.sale_order_count, 0)

        action = event.action_view_sale_order()
        self.assertEqual(action["res_id"], order.id)
        self.assertFalse(empty_event.action_view_sale_order()["res_id"])

    def test_view_sale_order_rejects_multi_event(self):
        events = self.env["calendar.event"].create(
            [
                {
                    "name": "First Meeting",
                    "start": datetime(2026, 7, 25, 10),
                    "stop": datetime(2026, 7, 25, 11),
                },
                {
                    "name": "Second Meeting",
                    "start": datetime(2026, 7, 25, 12),
                    "stop": datetime(2026, 7, 25, 13),
                },
            ]
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            events.action_view_sale_order()
