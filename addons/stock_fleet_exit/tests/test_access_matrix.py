from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

HAND_OVER = (
    "a route hands its vehicle over and back and writes where it stays only "
    "through stock_fleet_exit.privilege_exit_hand_over, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetExitAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "driver_a": Persona("stock_fleet.group_trip_driver"),
        "authoriser_a": Persona("stock_fleet_exit.group_fleet_exit_authoriser"),
        "stock_manager_a": Persona("stock.group_stock_manager"),
        "admin_a": Persona("base.group_system"),
    }
    cells = (
        Cell(
            "resource.resource",
            "vehicle_resource",
            note="the vehicle's own access stays as its modules grant it; " + HAND_OVER,
            employee_a="r",
            stock_user_a="r",
            driver_a="r",
            authoriser_a="r",
            stock_manager_a="r",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        kind = env.ref("base.kind_vehicle")
        product = env["product.product"].create(
            {"name": "Matrix Pickup", "type": "consu", "asset_kind_id": kind.id}
        )
        vehicle = env["resource.asset.vehicle"].create(
            {
                "name": "Matrix Pickup",
                "product_id": product.id,
                "company_id": cls.companies["a"].id,
            }
        )
        return {"vehicle_resource": vehicle.resource_id}
