from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale_renting.tests.common import TestWebsiteSaleRentingCommon


@tagged("post_install", "-at_install")
class TestOvernightRental(HttpCase, TestWebsiteSaleRentingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.hotel_room_early_check_in = cls._create_product(
            name="Hotel Room Early Birds",
            product_pricing_ids=[
                Command.create(
                    {"recurrence_id": cls.recurrence_night_15_10.id, "price": 90}
                ),
            ],
            is_published=True,
        )
        cls.hotel_room_late_check_in = cls._create_product(
            name="Hotel Room Night Owls",
            product_pricing_ids=[
                Command.create(
                    {"recurrence_id": cls.recurrence_night_18_9.id, "price": 70}
                ),
            ],
            is_published=True,
        )
        cls.bike_for_a_day = cls._create_product(
            name="Bike",
            product_pricing_ids=[
                Command.create({"recurrence_id": cls.recurrence_day.id, "price": 20}),
            ],
            is_published=True,
        )

    def test_add_to_cart_with_overnight_period(self):
        with freeze_time("2025-01-01"):
            with MockRequest(self.env, website=self.website) as request:
                self.env.user.partner_id = self.partner
                ro = request.website._create_cart()
                ro._cart_add(
                    product_id=self.bike_for_a_day.product_variant_id.id, quantity=1
                )
                self.assertFalse(
                    self.hotel_room_early_check_in._is_add_to_cart_allowed(),
                    "Overnight product should not be addable to cart with non-overnight product",
                )
                ro._cart_update_line_quantity(line_id=ro.line_ids[0].id, quantity=0)
                self.assertTrue(
                    self.hotel_room_early_check_in._is_add_to_cart_allowed(),
                    "Overnight product should be addable to empty cart",
                )
                ro._cart_add(product_id=self.hotel_room_early_check_in.id, quantity=1)
                self.assertFalse(
                    self.hotel_room_late_check_in._is_add_to_cart_allowed(),
                    "Overnight product with different period should not be addable to cart",
                )
                self.assertTrue(
                    self.hotel_room_early_check_in._is_add_to_cart_allowed(),
                    "Overnight product with same period should be addable to cart",
                )

    def test_get_default_renting_dates(self):
        with freeze_time("2025-01-01"):
            with MockRequest(self.env, website=self.website) as request:
                with patch.object(request, "cookies", {"tz": "Europe/Brussels"}):
                    start_date, end_date = (
                        self.hotel_room_early_check_in.product_tmpl_id._get_default_renting_dates(
                            start_date=None,
                            end_date=None,
                            duration=24,
                            unit="hour",
                            pickup_time=15,
                            return_time=10,
                        )
                    )
                    self.assertEqual(start_date.hour, 14)
                    self.assertEqual(end_date.hour, 9)
                    start_date, end_date = (
                        self.bike_for_a_day.product_tmpl_id._get_default_renting_dates(
                            start_date=None,
                            end_date=None,
                            duration=1,
                            unit="day",
                            pickup_time=False,
                            return_time=False,
                        )
                    )
                    self.assertEqual(start_date.hour, 23)
                    self.assertEqual(end_date.hour, 22)

            with MockRequest(self.env, website=self.website_2) as request:
                with patch.object(request, "cookies", {"tz": "America/New_York"}):
                    start_date, end_date = (
                        self.hotel_room_early_check_in.product_tmpl_id._get_default_renting_dates(
                            start_date=None,
                            end_date=None,
                            duration=24,
                            unit="hour",
                            pickup_time=15,
                            return_time=10,
                        )
                    )
                    self.assertEqual(start_date.hour, 20)
                    self.assertEqual(end_date.hour, 15)
                    start_date, end_date = (
                        self.bike_for_a_day.product_tmpl_id._get_default_renting_dates(
                            start_date=None,
                            end_date=None,
                            duration=1,
                            unit="day",
                            pickup_time=False,
                            return_time=False,
                        )
                    )
                    self.assertEqual(start_date.hour, 5)
                    self.assertEqual(end_date.hour, 4)

            with MockRequest(self.env, website=self.website) as request:
                with patch.object(request, "cookies", {"tz": "Europe/Brussels"}):
                    existing_start_date = fields.Datetime.to_datetime(
                        "2025-01-01 19:19:19"
                    )
                    existing_end_date = fields.Datetime.to_datetime(
                        "2025-01-02 11:11:11"
                    )
                    start_date, end_date = (
                        self.hotel_room_early_check_in.product_tmpl_id._get_default_renting_dates(
                            start_date=existing_start_date,
                            end_date=existing_end_date,
                            duration=24,
                            unit="hour",
                            pickup_time=15,
                            return_time=10,
                        )
                    )
                    self.assertEqual(start_date, existing_start_date)
                    self.assertEqual(end_date, existing_end_date)

    def test_rental_order_created_with_pickup_return_times(self):
        with freeze_time("2025-01-01"):
            with MockRequest(self.env, website=self.website) as request:
                self.env.user.partner_id = self.partner
                ro = request.website._create_cart()
                start_date, end_date = (
                    self.hotel_room_early_check_in.product_tmpl_id._get_default_renting_dates(
                        start_date=None,
                        end_date=None,
                        duration=24,
                        unit="hour",
                        pickup_time=15,
                        return_time=10,
                    )
                )
                ro._cart_add(
                    product_id=self.hotel_room_early_check_in.id,
                    quantity=1,
                    start_date=start_date,
                    end_date=end_date,
                )
                self.assertEqual(ro.rental_start_date.hour, 14)
                self.assertEqual(ro.rental_return_date.hour, 9)
