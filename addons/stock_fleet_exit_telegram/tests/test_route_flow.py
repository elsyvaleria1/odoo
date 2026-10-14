from odoo.tests import tagged

from odoo.addons.stock_fleet_exit.tests.common import FleetExitCommon
from odoo.addons.stock_fleet_exit_telegram.models.telegram_handler import (
    parse_odometer,
)
from odoo.addons.telegram.tests.common import TelegramBotTestCase

DRIVER_CHAT = "699101"
AUTHORISER_CHAT = "699102"


@tagged("post_install", "-at_install")
class TestRouteFlow(TelegramBotTestCase, FleetExitCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls._bound_account(
            DRIVER_CHAT, cls.driver_user.partner_id, user=cls.driver_user
        )
        cls._bound_account(
            AUTHORISER_CHAT, cls.authoriser.partner_id, user=cls.authoriser
        )
        cls.test_bot.command_ids = cls.env.ref(
            "stock_fleet_exit_telegram.command_rutas"
        )
        cls.passenger = cls.env["hr.employee"].create({"name": "Armando Pasajero"})
        cls.update_id = 8800

    def _update(self, payload):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {"update_id": self.update_id, **payload},
            )
        return "\n".join(
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        )

    def _say(self, text, chat=DRIVER_CHAT):
        return self._update(
            {
                "message": self.mock_telegram_message(
                    chat_id=chat, text=text, message_id=self.update_id
                )
            }
        )

    def _press(self, data, chat=DRIVER_CHAT):
        return self._update(
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id=chat
                )
            }
        )

    def _last_route(self):
        return self.Batch.search(
            [("vehicle_id", "=", self.vehicle.id), ("is_fleet_exit", "=", True)],
            limit=1,
        )

    def _ask_by_telegram(self):
        self._say("/ayuda", chat=AUTHORISER_CHAT)
        self._say("/rutas")
        self._press(f"rut:v:{self.vehicle.id}")
        self._press(f"rut:t:{self.emission.id}")
        self._press("rut:g:0")
        self._press(f"rut:t:{self.water.id}")
        self._press("rut:td")
        self._press("rut:pa")
        self._say("Armando")
        self._press(f"rut:pe:{self.passenger.id}")
        self._press("rut:pn")
        self._say("45,210 km")
        return self._press("rut:ok")

    def _queued_to(self, chat_id):
        chat = self.env["telegram.chat"].search(
            [("bot_id", "=", self.test_bot.id), ("chat_id", "=", chat_id)]
        )
        return self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("api_method", "=", "sendMessage")]
        )

    def test_a_driver_asks_for_a_route_with_its_activities_and_passengers(self):
        reply = self._ask_by_telegram()

        route = self._last_route()
        self.assertEqual(route.operator_id, self.driver)
        self.assertEqual(route.passenger_ids, self.passenger)
        self.assertEqual(route.odometer_departure, 45210.0)
        self.assertEqual(
            route._get_exit_activities().activity_type_id, self.water | self.emission
        )
        self.assertTrue(route._get_exit_authorisations())
        self.assertFalse(route.date_departure)
        self.assertIn("when it is authorised", reply)
        push = self._queued_to(AUTHORISER_CHAT).filtered(
            lambda message: "asks to leave" in (message.payload or {}).get("text", "")
        )
        self.assertTrue(push, "the authoriser is asked with the route's summary")
        self.assertIn(f"rut:A:{route.id}", str(push[:1].payload))

    def test_the_authoriser_decides_from_telegram(self):
        self._ask_by_telegram()
        route = self._last_route()

        reply = self._press(f"rut:A:{route.id}", chat=AUTHORISER_CHAT)

        self.assertEqual(route.trip_state, "in_transit")
        self.assertEqual(route.exit_authorised_uid, self.authoriser)
        self.assertEqual(self.vehicle.operator_employee_id, self.driver)
        self.assertIn("leaves now", reply)

    def test_a_refusal_from_telegram_cancels_it(self):
        self._ask_by_telegram()
        route = self._last_route()

        self._press(f"rut:R:{route.id}", chat=AUTHORISER_CHAT)

        self.assertEqual(route.state, "cancel")

    def test_out_the_driver_adds_a_passenger_and_registers_the_return(self):
        self._ask_by_telegram()
        route = self._last_route()
        self._authorise(route)
        other = self.env["hr.employee"].create({"name": "Gustavo Recogido"})

        self._say("/rutas")
        self._press("rut:mp")
        self._say("Gustavo")
        self._press(f"rut:pe:{other.id}")
        self.assertIn(other, route.passenger_ids)

        offer = self._say("/rutas")
        self.assertIn("What happened?", offer)
        self._press("rut:mr")
        self._press("rut:cn")
        reply = self._say("45260")

        self.assertEqual(route.state, "done")
        self.assertEqual(route.trip_distance, 50.0)
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)
        self.assertIn("registered", reply)

    def test_out_the_driver_adds_an_activity(self):
        self._ask_by_telegram()
        route = self._last_route()
        self._authorise(route)
        workshop = self.env.ref("stock_fleet_exit.activity_type_exit_workshop")

        self._say("/rutas")
        self._press("rut:ma")
        self._press(f"rut:t:{workshop.id}")

        self.assertIn(workshop, route._get_exit_activities().activity_type_id)

    def test_the_vehicle_stays_where_the_route_closes(self):
        self._ask_by_telegram()
        route = self._last_route()
        self._authorise(route)

        self._say("/rutas")
        self._press("rut:ms")
        self._press("rut:cn")
        self._say("45230")
        reply = self._say("Taller Mecánico Juárez")

        self.assertEqual(route.state, "done")
        self.assertEqual(route.exit_stay_location, "Taller Mecánico Juárez")
        self.assertEqual(self.vehicle.resource_id.location, "Taller Mecánico Juárez")
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)
        self.assertIn("stays at", reply)

    def test_closing_asks_who_rode_along_before_the_odometer(self):
        self._ask_by_telegram()
        route = self._last_route()
        self._authorise(route)
        forgotten = self.env["hr.employee"].create({"name": "Beto Olvidado"})

        self._say("/rutas")
        question = self._press("rut:mr")
        self.assertIn("who rode with you", question)
        self.assertIn("Armando Pasajero", question)
        self._press("rut:ca")
        self._say("Beto")
        again = self._press(f"rut:pe:{forgotten.id}")
        self.assertIn("Beto Olvidado", again)
        self.assertFalse(route.date_return)
        self._press("rut:cn")
        self._say("45260")

        self.assertEqual(route.state, "done")
        self.assertEqual(route.passenger_ids, self.passenger | forgotten)

    def test_a_waiting_request_can_be_withdrawn(self):
        self._ask_by_telegram()
        route = self._last_route()

        waiting = self._say("/rutas")
        self.assertIn("is waiting to be authorised", waiting)
        self._press(f"rut:x:{route.id}")

        self.assertEqual(route.state, "cancel")
        self.assertFalse(route._get_exit_authorisations())

    def test_a_driver_without_employee_is_told_why(self):
        self.driver.user_id = False

        reply = self._say("/rutas")

        self.assertIn("not linked to an employee", reply)

    def test_the_authorisers_hear_what_concerns_them(self):
        self._say("/ayuda", chat=AUTHORISER_CHAT)

        sent = self.Batch._notify_authorisers(
            lambda route: route.env._("Left without a route"), self.env.company
        )

        self.assertGreaterEqual(sent, 1)

    def test_odometer_readings_are_read_as_people_type_them(self):
        self.assertEqual(parse_odometer("45,210 km"), 45210.0)
        self.assertEqual(parse_odometer("45.210"), 45210.0)
        self.assertEqual(parse_odometer("1.234.567"), 1234567.0)
        self.assertEqual(parse_odometer("45210,5"), 45210.5)
        self.assertEqual(parse_odometer("km 45 210"), 45210.0)
        self.assertEqual(parse_odometer("152.5"), 152.5)
        self.assertIsNone(parse_odometer("lleno"))
