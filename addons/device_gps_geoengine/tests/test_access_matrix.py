from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

REFERENCE = "reference data a GPS user reads and a GPS manager maintains"
ADDRESS = (
    "a GPS user locates a device they read; the street address of its last "
    "position is cached on it only through "
    "device_gps_geoengine.privilege_cache_current_address, which no user holds"
)
TRAIL = (
    "the trail wizard's and its result's rows grant every GPS user the whole "
    "model, with no reach to the one who drew the trail: any GPS user, of any "
    "company, reads, rewrites and deletes another's trail, a company-guarded "
    "device's GPS track included"
)
PARCEL = json_dumps(
    [[19.39, -99.11], [19.41, -99.11], [19.41, -99.09], [19.39, -99.09]]
)


@tagged("post_install", "-at_install", "access_matrix")
class TestDeviceGpsGeoengineAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "gps_user_a": Persona("device_gps.group_device_gps_user"),
        "editor_a": Persona("device_gps_geoengine.group_device_gps_geofence_editor"),
        "gps_manager_a": Persona("device_gps.group_device_gps_manager"),
        "gps_user_b": Persona("device_gps.group_device_gps_user", company="b"),
        "portal_c": Persona(portal="customer_c"),
    }
    cells = (
        Cell(
            "device.state.boundary",
            "boundary",
            note=REFERENCE,
            gps_user_a="r",
            editor_a="r",
            gps_manager_a="rwcd",
            gps_user_b="r",
        ),
        Cell(
            "device.weekday",
            "weekday",
            note=REFERENCE,
            gps_user_a="r",
            editor_a="r",
            gps_manager_a="rwcd",
            gps_user_b="r",
        ),
        Cell(
            "device.geo.fence",
            "fence_a",
            note="a geofence editor draws and changes geofences, only a GPS "
            "manager deletes one",
            gps_user_a="r",
            editor_a="rwc",
            gps_manager_a="rwcd",
        ),
        Cell(
            "device.geo.fence",
            "fence_b",
            gps_user_b="r",
        ),
        Cell(
            "device.geo.fence",
            "fence_shared",
            note="a geofence without a company is every company's",
            gps_user_a="r",
            editor_a="rwc",
            gps_manager_a="rwcd",
            gps_user_b="r",
        ),
        Cell(
            "device.client.visit",
            "visit_a",
            note="a visit is recorded by the visit tracking, and belongs to its "
            "device's company",
            gps_user_a="r",
            editor_a="r",
            gps_manager_a="rwcd",
        ),
        Cell(
            "device.client.visit",
            "visit_b",
            gps_user_b="r",
        ),
        Cell(
            "device.device",
            "device_a",
            note=ADDRESS,
            gps_user_a="r locate",
            editor_a="r locate",
            gps_manager_a="rwcd locate",
        ),
        Cell(
            "device.device",
            "device_b",
            note=ADDRESS,
            gps_user_b="r locate",
        ),
        Cell(
            "wizard.device.device.view.trail",
            "trail_own",
            finding=TRAIL,
            gps_user_a="rwcd",
            today={"editor_a": "rwcd", "gps_manager_a": "rwcd", "gps_user_b": "rwcd"},
        ),
        Cell(
            "wizard.device.device.view.trail",
            "trail_other",
            finding=TRAIL,
            gps_manager_a="rwcd",
            today={"gps_user_a": "rwcd", "editor_a": "rwcd", "gps_user_b": "rwcd"},
        ),
        Cell(
            "wizard.device.device.view.trail.result",
            "trail_result_own",
            finding=TRAIL,
            gps_user_a="rwcd",
            today={"editor_a": "rwcd", "gps_manager_a": "rwcd", "gps_user_b": "rwcd"},
        ),
        Cell(
            "wizard.device.device.view.trail.result",
            "trail_result_other",
            finding=TRAIL,
            gps_manager_a="rwcd",
            today={"gps_user_a": "rwcd", "editor_a": "rwcd", "gps_user_b": "rwcd"},
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        profile = env["device.profile"].create({"name": "matrix profile"})
        client = cls.partners["customer_c"]

        def device(identifier, company):
            record = env["device.device"].create(
                {
                    "name": f"matrix tracker {identifier}",
                    "identifier": identifier,
                    "config_id": profile.id,
                    "comm_protocol": "http",
                    "imei": f"MATRIX-IMEI-{identifier}",
                    "device_category_id": env.ref("device.device_category_gps").id,
                    "company_id": company.id,
                }
            )
            record.log_gps_last_id = env["device.data.log.gps"].create(
                {"device_id": record.id, "latitude": 19.40, "longitude": -99.10}
            )
            return record

        def fence(name, company):
            return env["device.geo.fence"].create(
                {
                    "name": name,
                    "area_type": "parcel",
                    "geofence_type": "polygon",
                    "schedule_type": "always",
                    "partner_id": client.id,
                    "polygon_points": PARCEL,
                    "company_id": company and company.id,
                }
            )

        def visit(device_record, fence_record):
            return env["device.client.visit"].create(
                {
                    "device_id": device_record.id,
                    "partner_id": client.id,
                    "geofence_id": fence_record.id,
                    "arrival": "2026-09-01 08:00:00",
                }
            )

        def trail(persona):
            user = cls.users[persona]
            wizard = (
                env["wizard.device.device.view.trail"]
                .with_user(user)
                .create({"device_ids": [Command.set(device_a.ids)]})
            )
            result = (
                env["wizard.device.device.view.trail.result"]
                .with_user(user)
                .create({"name": f"matrix trail {persona}", "device_id": device_a.id})
            )
            return wizard.with_env(env), result.with_env(env)

        device_a, device_b = device("MATRIX-A", a), device("MATRIX-B", b)
        trail_own, trail_result_own = trail("gps_user_a")
        trail_other, trail_result_other = trail("gps_manager_a")
        fence_a, fence_b = fence("matrix parcel a", a), fence("matrix parcel b", b)
        return {
            "boundary": env["device.state.boundary"].create(
                {"name": "matrix boundary", "country_id": env.ref("base.mx").id}
            ),
            "weekday": env["device.weekday"].search([], limit=1),
            "fence_a": fence_a,
            "fence_b": fence_b,
            "fence_shared": fence("matrix shared parcel", False),
            "visit_a": visit(device_a, fence_a),
            "visit_b": visit(device_b, fence_b),
            "device_a": device_a,
            "device_b": device_b,
            "trail_own": trail_own,
            "trail_other": trail_other,
            "trail_result_own": trail_result_own,
            "trail_result_other": trail_result_other,
        }
