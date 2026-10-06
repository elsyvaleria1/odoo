from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

PRIVILEGE = "stock_fleet_trace_gps_geoengine.privilege_trip_track, which no user holds"
TRACK = "a trip reads its vehicle's GPS device only through " + PRIVILEGE
TRAIL = (
    "device_gps_geoengine's trail wizard and result rows grant every GPS user "
    "the whole model, with no reach to the one who drew the trail: a GPS user "
    "reads, rewrites and deletes the track a stock user drew of a trip"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetTraceGpsGeoengineAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "stock_manager_a": Persona("stock.group_stock_manager"),
        "gps_user_a": Persona("device_gps.group_device_gps_user"),
        "stock_user_b": Persona("stock.group_stock_user", company="b"),
    }
    cells = (
        Cell(
            "device.data.log.gps",
            "gps_observation_a",
            note="a trip draws its track from the vehicle's observations only through "
            "stock_fleet_trace_gps_geoengine.privilege_trip_track",
            needs="the GPS observations, which live in the remote GPS database",
        ),
        Cell(
            "stock.picking.batch",
            "batch_a",
            note="a stock user views the GPS track of a trip they read",
            stock_user_a="rwcd view_gps_track",
            stock_manager_a="rwcd view_gps_track",
        ),
        Cell(
            "device.device",
            "vehicle_tracker_a",
            note=TRACK,
            gps_user_a="r locate",
        ),
        Cell(
            "device.data.log.gps",
            "vehicle_position_a",
            note="a trip reads its vehicle's GPS observations only through "
            + PRIVILEGE,
            gps_user_a="r",
        ),
        Cell(
            "wizard.device.device.view.trail",
            "trail_wizard_trip",
            note="a trip draws its track only through " + PRIVILEGE,
            finding=TRAIL,
            today={"gps_user_a": "rwcd"},
        ),
        Cell(
            "wizard.device.device.view.trail.result",
            "trail_trip",
            note="a stock user reads the trip tracks they drew, handed over "
            "without their device",
            finding=TRAIL,
            stock_user_a="r",
            today={"gps_user_a": "rwcd"},
        ),
        Cell(
            "wizard.device.device.view.trail.result",
            "trail_with_device",
            note="a trail still naming its device is not a trip track",
            finding=TRAIL,
            today={"gps_user_a": "rwcd"},
        ),
        Cell(
            "wizard.stock.trip.track.point",
            "point_stock_user",
            note="the points of a track are read by the one who drew it",
            stock_user_a="r",
        ),
        Cell(
            "wizard.stock.trip.track.point",
            "point_gps_user",
            note="the points of a track are read by the one who drew it",
            gps_user_a="r",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a = cls.companies["a"]
        batch = env["stock.picking.batch"].with_company(a).create({"company_id": a.id})
        tracker = env["device.device"].create(
            {
                "name": "matrix vehicle tracker",
                "identifier": "MATRIX-TRIP-A",
                "config_id": env["device.profile"]
                .create({"name": "matrix trip profile"})
                .id,
                "comm_protocol": "http",
                "company_id": a.id,
            }
        )

        def drawn_by(persona, model):
            return (
                env[model]
                .with_user(cls.users[persona])
                .with_privilege(
                    "stock_fleet_trace_gps_geoengine.privilege_trip_track",
                    reason="the matrix draws a trip's track as the trip does",
                )
            )

        def point(persona):
            return (
                drawn_by(persona, "wizard.stock.trip.track.point")
                .create(
                    {
                        "name": f"matrix stop {persona}",
                        "batch_id": batch.id,
                        "kind": "stop",
                    }
                )
                .with_env(env)
            )

        def result(persona, device):
            return (
                drawn_by(persona, "wizard.device.device.view.trail.result")
                .create({"name": f"matrix trip {persona}", "device_id": device.id})
                .with_env(env)
            )

        return {
            "gps_observation_a": None,
            "batch_a": batch,
            "vehicle_tracker_a": tracker,
            "vehicle_position_a": env["device.data.log.gps"].create(
                {
                    "device_id": tracker.id,
                    "timestamp": "2026-09-28 08:00:00",
                    "latitude": 19.3,
                    "longitude": -99.6,
                }
            ),
            "trail_wizard_trip": drawn_by(
                "stock_user_a", "wizard.device.device.view.trail"
            )
            .create({"device_ids": [Command.set(tracker.ids)]})
            .with_env(env),
            "trail_trip": result("stock_user_a", env["device.device"]),
            "trail_with_device": result("stock_user_a", tracker),
            "point_stock_user": point("stock_user_a"),
            "point_gps_user": point("gps_user_a"),
        }
