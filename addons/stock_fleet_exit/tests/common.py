from odoo.tests import TransactionCase, new_test_user


class FleetExitCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.fleet_exit_log = True
        cls.route_type = cls.warehouse.fleet_exit_type_id
        cls.driver_user = new_test_user(
            cls.env, login="route_driver", groups="stock_fleet.group_trip_driver"
        )
        cls.authoriser = new_test_user(
            cls.env,
            login="route_authoriser",
            groups="stock_fleet_exit.group_fleet_exit_authoriser",
        )
        cls.second_authoriser = new_test_user(
            cls.env,
            login="route_authoriser_two",
            groups="stock_fleet_exit.group_fleet_exit_authoriser",
        )
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        cls.holder = cls.env["hr.employee"].create({"name": "Usual Operator"})
        kind = cls.env.ref("base.kind_vehicle")
        product = cls.env["product.product"].create(
            {"name": "Pickup", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].create(
            {
                "name": "Pickup LF-01",
                "product_id": product.id,
                "operator_employee_id": cls.holder.id,
            }
        )
        cls.water = cls.env.ref("stock_fleet_exit.activity_type_exit_errand_water")
        cls.emission = cls.env.ref("stock_fleet_exit.activity_type_exit_emission_check")
        cls.Batch = cls.env["stock.picking.batch"]

    def _route(self, user=None, activities=None, **vals):
        user = user or self.driver_user
        route = self.Batch.with_user(user).create(
            {
                "picking_type_id": self.route_type.id,
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "odometer_departure": 1000.0,
                **vals,
            }
        )
        for activity_type in self.water if activities is None else activities:
            route._add_exit_activity(activity_type)
        return route.with_env(self.env)

    def _ask(self, **vals):
        route = self._route(**vals)
        route.with_user(self.driver_user).action_exit_request()
        return route

    def _authorise(self, route, user=None):
        route.with_user(user or self.authoriser).action_exit_authorise()
