from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import FleetExitCommon


@tagged("post_install", "-at_install")
class TestFleetExit(FleetExitCommon):
    def test_a_warehouse_with_an_exit_log_gets_its_routes_type(self):
        self.assertTrue(self.route_type.fleet_exit)
        self.assertTrue(self.route_type.dispatch_management)
        self.assertEqual(self.route_type.warehouse_id, self.warehouse)

    def test_a_route_is_numbered_by_year_and_month(self):
        route = self._route()

        today = fields.Date.context_today(route)
        self.assertRegex(route.name, rf"^RUTA/{today:%y}/{today:%m}/\d{{4}}$")

    def test_asking_schedules_one_authorisation_per_authoriser(self):
        route = self._ask()

        asked = route._get_exit_authorisations()
        self.assertLessEqual(self.authoriser | self.second_authoriser, asked.user_id)
        self.assertNotIn(self.driver_user, asked.user_id)
        self.assertFalse(route.date_departure)
        self.assertEqual(route.exit_requested_uid, self.driver_user)

    def test_a_route_does_not_leave_without_its_authorisation(self):
        route = self._route()

        with self.assertRaisesRegex(UserError, "authorises it"):
            route.action_depart()

    def test_the_first_authorisation_departs_it_and_withdraws_the_others(self):
        route = self._ask()

        self._authorise(route)

        self.assertEqual(route.trip_state, "in_transit")
        self.assertTrue(route.date_departure)
        self.assertEqual(route.supervisor_id, self.authoriser)
        self.assertEqual(route.exit_authorised_uid, self.authoriser)
        self.assertFalse(route._get_exit_authorisations())
        self.assertEqual(self.vehicle.operator_employee_id, self.driver)
        self.assertEqual(route.exit_holder_id, self.holder)
        with self.assertRaisesRegex(UserError, "not waiting for your authorisation"):
            route.with_user(self.second_authoriser).action_exit_authorise()

    def test_a_refusal_cancels_the_route(self):
        route = self._ask()

        route.with_user(self.second_authoriser).action_exit_refuse("No hay chofer")

        self.assertEqual(route.state, "cancel")
        self.assertFalse(route.date_departure)
        self.assertFalse(route._get_exit_authorisations())
        self.assertFalse(route._get_exit_activities(done=False))
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)

    def test_back_at_the_warehouse_the_vehicle_returns_to_its_operator(self):
        route = self._ask(activities=self.water | self.emission)
        self._authorise(route)

        route.with_user(self.driver_user).odometer_return = 1042.0
        route.with_user(self.driver_user).action_return()

        self.assertEqual(route.state, "done")
        self.assertEqual(route.trip_distance, 42.0)
        self.assertTrue(route.trip_hours >= 0)
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)
        self.assertEqual(len(route._get_exit_activities(done=True)), 2)
        self.assertFalse(route._get_exit_activities(done=False))

    def test_a_route_closed_where_the_vehicle_stays_names_its_location(self):
        self.vehicle.resource_id.location = "Cochera CDG"
        route = self._ask()
        self._authorise(route)
        route.write({"odometer_return": 1010.0, "exit_stay_location": "Agencia Toyota"})

        route.action_exit_close_here()

        self.assertEqual(self.vehicle.resource_id.location, "Agencia Toyota")
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)
        back = self._ask(
            activities=self.env.ref("stock_fleet_exit.activity_type_exit_return_cdg"),
            odometer_departure=1010.0,
        )
        self._authorise(back)
        back.write({"odometer_return": 1025.0})
        back.action_return()
        self.assertEqual(self.vehicle.resource_id.location, "Cochera CDG")

    def test_closing_where_it_stays_needs_the_place(self):
        route = self._ask()
        self._authorise(route)
        route.odometer_return = 1010.0

        with self.assertRaisesRegex(UserError, "Say where"):
            route.action_exit_close_here()

    def test_passengers_and_activities_join_while_it_is_out(self):
        route = self._ask()
        self._authorise(route)
        passenger = self.env["hr.employee"].create({"name": "Armando"})

        route.with_user(self.driver_user).passenger_ids = passenger
        route.with_user(self.driver_user)._add_exit_activity(self.emission)

        self.assertEqual(route.passenger_ids, passenger)
        self.assertIn("Emissions Check Centre", route.exit_activity_summary)
        self.assertIn("Errand / Water", route.exit_activity_summary)

    def test_a_route_asks_to_leave_with_what_it_goes_to_do(self):
        route = self._route(activities=self.env["mail.activity.type"])

        with self.assertRaisesRegex(UserError, "Route activities"):
            route.with_user(self.driver_user).action_exit_request()

    def test_a_vehicle_waits_for_one_route_at_a_time(self):
        self._ask()

        with self.assertRaisesRegex(UserError, "is already on"):
            self._ask()

    def test_the_route_activities_done_stay_for_the_log(self):
        route = self._ask()
        self._authorise(route)
        route.odometer_return = 1001.0
        route.action_return()

        done = (
            self.env["mail.activity"]
            .with_context(active_test=False)
            .search(
                [
                    ("res_model", "=", "stock.picking.batch"),
                    ("activity_type_id.fleet_exit_role", "=", "destination"),
                    ("res_id", "=", route.id),
                ]
            )
        )
        self.assertEqual(done.activity_type_id, self.water)
        self.assertTrue(done.date_done)
