import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.libs import sealing
from odoo.tests import TransactionCase, tagged

TZ = ZoneInfo("America/Mexico_City")
LEG = 10_000


def tomtom_answer(seconds, order=None):
    answer = {
        "routes": [
            {
                "legs": [
                    {
                        "summary": {
                            "travelTimeInSeconds": leg,
                            "trafficDelayInSeconds": 0,
                            "lengthInMeters": LEG,
                        }
                    }
                    for leg in seconds
                ]
            }
        ]
    }
    if order is not None:
        answer["optimizedWaypoints"] = [
            {"providedIndex": provided, "optimizedIndex": optimized}
            for optimized, provided in enumerate(order)
        ]
    return answer


@tagged("post_install", "-at_install")
class TestTripRoute(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)
        cls.tomtom_credential = cls.env["credential.credential"].create(
            {
                "name": "TomTom",
                "endpoint_id": cls.env.ref(
                    "stock_fleet_route.service_tomtom_routing"
                ).id,
                "environment": "production",
                "api_key": "test-key",
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.write(
            {
                "trip_origin_latitude": 19.315213,
                "trip_origin_longitude": -99.598715,
                "route_service_minutes": 30,
            }
        )
        cls.warehouse.partner_id.tz = "America/Mexico_City"
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write({"dispatch_management": True, "trip_trace": False})
        cls.supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "route_supervisor",
                "lang": "en_US",
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_manager").id])
                ],
            }
        )
        cls.seller = cls.env["res.users"].create(
            {
                "name": "Seller",
                "login": "route_seller",
                "lang": "en_US",
                "group_ids": [
                    Command.set([cls.env.ref("sale.group_sale_salesman").id])
                ],
            }
        )
        cls.driver_user = cls.env["res.users"].create(
            {
                "name": "Driver",
                "login": "route_driver",
                "lang": "en_US",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        kind = cls.env.ref("base.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Route Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertiliser", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 1000
        )
        mx = cls.env.ref("base.mx")
        cls.customer_a = cls._customer("Customer A", 19.30, -99.60, "3311111111", mx)
        cls.customer_b = cls._customer("Customer B", 19.35, -99.55, "3322222222", mx)
        cls.customer_c = cls._customer("Customer C", 19.28, -99.65, "3333333333", mx)
        cls.customer_far = cls._customer("Customer Nowhere", 0, 0, None, mx)
        cls._telegram_setup()

    @classmethod
    def _customer(cls, name, latitude, longitude, phone, country):
        return cls.env["res.partner"].create(
            {
                "name": name,
                "lang": "en_US",
                "country_id": country.id,
                "partner_latitude": latitude,
                "partner_longitude": longitude,
                "phone_ids": [Command.create({"number": phone, "type": "mobile"})]
                if phone
                else [],
            }
        )

    @classmethod
    def _telegram_setup(cls):
        credential = cls.env["credential.credential"].create(
            {
                "name": "Route Bot",
                "category_id": cls.env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": cls.env.ref("telegram.service_telegram").id,
                "bearer_token": "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            }
        )
        cls.bot = cls.env["telegram.bot"].create(
            {"name": "Route Bot", "credential_id": credential.id}
        )
        cls.chats = {}
        for chat_id, user in (
            ("101", cls.seller),
            ("102", cls.supervisor),
            ("103", cls.driver_user),
        ):
            account = cls.env["telegram.account"].create({"tg_user_id": chat_id})
            cls.env["telegram.binding"].create(
                {
                    "account_id": account.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "method": "session",
                }
            )
            cls.env["telegram.chat"].create(
                {
                    "chat_id": chat_id,
                    "chat_type": "private",
                    "bot_id": cls.bot.id,
                    "account_id": account.id,
                }
            )
            cls.chats[chat_id] = user

    def _delivery(self, customer):
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "user_id": self.seller.id,
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        picking = order.picking_ids
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        return picking

    def _trip(self, pickings, **vals):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1000.0,
                **vals,
            }
        )

    def _tomtom(self, *answers):
        calls = []
        answers = list(answers)

        def fake(model, connection, path, params):
            calls.append((path, params))
            return answers.pop(0)

        patcher = patch.object(
            type(self.env["stock.fleet.route.tomtom"]), "_tomtom_request", fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def _telegram(self):
        sent = []

        def fake(bot, chat_id, text, reply_markup=None, parse_mode="Markdown"):
            sent.append((self.chats[chat_id], text))
            return {"ok": True}

        patcher = patch.object(type(self.env["telegram.bot"]), "send_message", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return sent

    @staticmethod
    def _local_to_utc(date):
        return date.replace(tzinfo=TZ).astimezone(UTC).replace(tzinfo=None)

    def _tomorrow_at(self, hour):
        today = datetime.now(TZ).date() + timedelta(days=1)
        return self._local_to_utc(datetime(today.year, today.month, today.day, hour))

    def test_suggest_applies_the_best_order_and_cumulative_etas(self):
        a = self._delivery(self.customer_a)
        b = self._delivery(self.customer_b)
        c = self._delivery(self.customer_c)
        start = self._tomorrow_at(8)
        trip = self._trip(a | b | c, date_planned=start)
        a.batch_sequence, b.batch_sequence, c.batch_sequence = 1, 2, 3
        calls = self._tomtom(tomtom_answer([600, 1200, 900, 1800], order=[2, 0, 1]))

        trip.with_user(self.supervisor).action_route_suggest()

        path, params = calls[0]
        self.assertTrue(path.startswith("/routing/1/calculateRoute/"))
        self.assertTrue(path.endswith("19.315213,-99.598715/json"))
        self.assertEqual(params["computeBestOrder"], "true")
        self.assertEqual(params["travelMode"], "truck")
        self.assertEqual(
            (c | a | b).mapped("batch_sequence"), [1, 2, 3], "C, A, B in that order"
        )
        service = timedelta(minutes=30)
        self.assertEqual(c.trip_eta, start + timedelta(seconds=600))
        self.assertEqual(a.trip_eta, c.trip_eta + service + timedelta(seconds=1200))
        self.assertEqual(b.trip_eta, a.trip_eta + service + timedelta(seconds=900))
        self.assertEqual(a.trip_eta_notified, a.trip_eta)
        self.assertEqual(trip.route_total_minutes, (600 + 1200 + 900 + 1800) / 60 + 90)
        self.assertEqual(trip.route_distance_km, 40.0)
        self.assertTrue(trip.route_computed_at)
        self.assertFalse(trip.route_warning)

    def test_suggest_leaves_customers_without_coordinates_at_the_end(self):
        a = self._delivery(self.customer_a)
        nowhere = self._delivery(self.customer_far)
        b = self._delivery(self.customer_b)
        trip = self._trip(a | nowhere | b, date_planned=self._tomorrow_at(18))
        a.batch_sequence, nowhere.batch_sequence, b.batch_sequence = 1, 2, 3
        calls = self._tomtom(tomtom_answer([600, 3600, 600], order=[1, 0]))

        trip.action_route_suggest()

        self.assertNotIn("0.0,0.0", calls[0][0])
        self.assertEqual((b | a | nowhere).mapped("batch_sequence"), [1, 2, 3])
        self.assertFalse(nowhere.trip_eta)
        self.assertIn("Customer Nowhere", trip.route_warning)
        self.assertIn("Does not make it within the day: Customer A", trip.route_warning)

    def _egress(self, answer):
        sent = []

        def fake(connection, method, url, **kwargs):
            sent.append((connection, url, kwargs["params"]))
            if isinstance(answer, Exception):
                raise answer
            return Mock(ok=True, json=lambda: answer)

        patcher = patch.object(
            type(self.env["integration.connection"]), "_egress_request", fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return sent

    def test_suggest_sends_the_key_of_the_company_credential(self):
        trip = self._trip(self._delivery(self.customer_a))
        sent = self._egress(tomtom_answer([600, 600]))

        trip.with_user(self.supervisor).action_route_suggest()

        connection, url, params = sent[0]
        self.assertEqual(connection.credential_id, self.tomtom_credential)
        self.assertTrue(
            url.startswith("https://api.tomtom.com/routing/1/calculateRoute/")
        )
        self.assertEqual(params["key"].reveal(), "test-key")
        self.assertEqual(params["travelMode"], "truck")

    def test_suggest_without_api_key_raises(self):
        self.tomtom_credential.active = False
        trip = self._trip(self._delivery(self.customer_a))
        with self.assertRaisesRegex(UserError, "No TomTom API key"):
            trip.action_route_suggest()

    def test_suggest_ignores_the_credential_of_another_company(self):
        self.tomtom_credential.company_id = self.env["res.company"].create(
            {"name": "Another Company"}
        )
        trip = self._trip(self._delivery(self.customer_a))
        with self.assertRaisesRegex(UserError, "No TomTom API key"):
            trip.action_route_suggest()

    def test_unreachable_tomtom_does_not_show_the_key(self):
        trip = self._trip(self._delivery(self.customer_a))
        self._egress(
            requests.ConnectionError(
                "Max retries exceeded with url: /routing/1/calculateRoute/"
                "19.3,-99.6:19.3,-99.6/json?key=test-key&traffic=true"
            )
        )
        with self.assertRaises(UserError) as raised:
            trip.action_route_suggest()
        self.assertIn("TomTom could not be reached", str(raised.exception))
        self.assertNotIn("test-key", str(raised.exception))

    def test_tomtom_error_becomes_a_user_error(self):
        trip = self._trip(self._delivery(self.customer_a))

        def fail(model, connection, path, params):
            raise UserError("TomTom answered: Invalid key")

        with (
            patch.object(
                type(self.env["stock.fleet.route.tomtom"]), "_tomtom_request", fail
            ),
            self.assertRaisesRegex(UserError, "Invalid key"),
        ):
            trip.action_route_suggest()

    def test_google_maps_url_follows_the_trip_order(self):
        a = self._delivery(self.customer_a)
        b = self._delivery(self.customer_b)
        c = self._delivery(self.customer_c)
        trip = self._trip(a | b | c)
        c.batch_sequence, a.batch_sequence, b.batch_sequence = 1, 2, 3

        action = trip.action_route_google_maps()

        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(
            action["url"],
            "https://www.google.com/maps/dir/?api=1"
            "&origin=19.315213,-99.598715"
            "&destination=19.35,-99.55"
            "&waypoints=19.28,-99.65|19.3,-99.6"
            "&travelmode=driving",
        )

    def test_departure_tells_the_seller_with_a_whatsapp_link(self):
        a = self._delivery(self.customer_a)
        nowhere = self._delivery(self.customer_far)
        trip = self._trip(a | nowhere, date_planned=self._tomorrow_at(8))
        self._tomtom(tomtom_answer([600, 600]))
        trip.action_route_suggest()
        sent = self._telegram()

        trip.action_depart()

        self.assertEqual([user for user, _text in sent], [self.seller, self.seller])
        text_a = next(text for _user, text in sent if a.name in text)
        hour = a.trip_eta.replace(tzinfo=UTC).astimezone(TZ).strftime("%H:%M")
        customer_text = (
            f"Tu pedido AgroMarin ya está en camino. Hora estimada de llegada: {hour}."
        )
        self.assertIn(f"https://wa.me/523311111111?text={quote(customer_text)}", text_a)
        text_nowhere = next(text for _user, text in sent if nowhere.name in text)
        self.assertIn("Estimated arrival: today", text_nowhere)
        self.assertIn("has no phone number", text_nowhere)
        self.assertNotIn("wa.me", text_nowhere)

    def _departed_trip_with_gps(self, **trip_vals):
        a = self._delivery(self.customer_a)
        b = self._delivery(self.customer_b)
        trip = self._trip(a | b, **trip_vals)
        a.batch_sequence, b.batch_sequence = 1, 2
        now = fields.Datetime.now()
        a.trip_eta = a.trip_eta_notified = now + timedelta(minutes=20)
        b.trip_eta = b.trip_eta_notified = now + timedelta(minutes=80)
        self._telegram()
        trip.action_depart()
        device = self.env["device.device"].create(
            {"name": "Truck GPS", "identifier": "ROUTE-GPS-1"}
        )
        with patch.object(fields.Datetime, "now", lambda: now - timedelta(days=1)):
            trip.vehicle_id.gps_device_id = device
        self.env["device.data.log.gps"].create(
            {
                "device_id": device.id,
                "latitude": 19.31,
                "longitude": -99.59,
                "timestamp": now - timedelta(minutes=2),
            }
        )
        return trip, a, b

    def test_refresh_reports_a_delay_above_the_threshold(self):
        trip, a, b = self._departed_trip_with_gps()
        baseline_b = b.trip_eta_notified
        calls = self._tomtom(tomtom_answer([25 * 60, 50 * 60]))
        sent = self._telegram()

        with patch.object(
            fields.Datetime, "now", lambda: baseline_b - timedelta(minutes=80)
        ):
            self.env["stock.picking.batch"]._cron_route_refresh_eta()

        self.assertEqual(calls[0][1]["computeBestOrder"], "false")
        self.assertTrue(calls[0][0].split("/")[-2].startswith("19.31,-99.59:"))
        self.assertEqual(b.trip_eta, baseline_b + timedelta(minutes=25))
        self.assertEqual(b.trip_eta_notified, b.trip_eta, "The baseline moves on.")
        self.assertEqual(
            a.trip_eta_notified, a.trip_eta - timedelta(minutes=5), "A stays put."
        )
        self.assertEqual(
            {user for user, _text in sent},
            {self.supervisor, self.driver_user, self.seller},
        )
        self.assertEqual(len(sent), 3, "Only B is late enough to tell anyone.")
        crew_text = dict(sent)[self.supervisor]
        self.assertIn(f"Delay on {trip.name}: Customer B", crew_text)
        self.assertIn("(+25 min)", crew_text)
        seller_text = dict(sent)[self.seller]
        self.assertIn("https://wa.me/523322222222?text=", seller_text)
        self.assertIn(
            quote("tu pedido AgroMarin llegará aproximadamente 25 minutos más tarde"),
            seller_text,
        )

    def test_a_seller_driving_their_trip_hears_of_the_delay_once(self):
        seller_driver = self.env["hr.employee"].create(
            {"name": "Seller driving", "user_id": self.seller.id}
        )
        _trip, _a, b = self._departed_trip_with_gps(operator_id=seller_driver.id)
        baseline_b = b.trip_eta_notified
        self._tomtom(tomtom_answer([25 * 60, 50 * 60]))
        sent = self._telegram()

        with patch.object(
            fields.Datetime, "now", lambda: baseline_b - timedelta(minutes=80)
        ):
            self.env["stock.picking.batch"]._cron_route_refresh_eta()

        self.assertEqual(
            sorted(user.login for user, _text in sent),
            sorted([self.supervisor.login, self.seller.login]),
        )
        self.assertIn("wa.me", dict(sent)[self.seller])

    def test_refresh_below_the_threshold_tells_nobody(self):
        trip, a, _b = self._departed_trip_with_gps()
        baseline = a.trip_eta_notified
        self._tomtom(tomtom_answer([30 * 60, 20 * 60]))
        sent = self._telegram()

        with patch.object(
            fields.Datetime, "now", lambda: baseline - timedelta(minutes=20)
        ):
            trip.with_user(self.supervisor).action_route_refresh_eta()

        self.assertFalse(sent)
        self.assertEqual(a.trip_eta, baseline + timedelta(minutes=10))
        self.assertEqual(a.trip_eta_notified, baseline)

    def test_refresh_without_a_recent_position_raises(self):
        trip, _a, _b = self._departed_trip_with_gps()
        self.env["device.data.log.gps"].search(
            [("device_id", "=", trip.vehicle_id.gps_device_id.id)]
        ).timestamp = fields.Datetime.now() - timedelta(hours=2)
        with self.assertRaisesRegex(UserError, "no GPS position"):
            trip.action_route_refresh_eta()
