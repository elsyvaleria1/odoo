from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.device_gps.tests.route_simulator import RouteSimulator, make_gps_device

READ = (
    "a route reads where its vehicle is and the geofence it stands in only "
    "through stock_fleet_exit_gps.privilege_exit_gps_read, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetExitGpsAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "authoriser_a": Persona("stock_fleet_exit.group_fleet_exit_authoriser"),
        "admin_a": Persona("base.group_system"),
    }
    cells = (
        Cell(
            "device.geo.fence",
            "geofence",
            note="geofences keep their access; " + READ,
            admin_a="rwcd",
        ),
        Cell(
            "device.data.log.gps",
            "gps_log",
            note="the track keeps its access; " + READ,
            admin_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        geofence = env["device.geo.fence"].create(
            {
                "name": "Matrix Agencia",
                "geofence_type": "circle",
                "center_latitude": 19.25,
                "center_longitude": -99.61,
                "radius": 200,
            }
        )
        kind = env.ref("base.kind_vehicle")
        product = env["product.product"].create(
            {"name": "Matrix Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        vehicle = env["resource.asset.vehicle"].create(
            {"name": "Matrix Truck", "product_id": product.id}
        )
        device = make_gps_device(env, vehicle, "SIM-MATRIX-1")
        RouteSimulator(
            env,
            device,
            start=fields.Datetime.now() - timedelta(hours=1),
            latitude=19.25,
            longitude=-99.61,
            odometer_km=10.0,
            fuel_percent=50.0,
        ).dwell(2, ignition=True)
        log = env["device.data.log.gps"].search(
            [("device_id", "=", device.id)], limit=1
        )
        return {"geofence": geofence, "gps_log": log}
