from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged

NORTHERN_LATITUDE = 32.7
NORTHERN_LONGITUDE = -115.5
PARCEL_HALF_SIDE = 0.001


@tagged("post_install", "-at_install")
class TestClientProximity(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["device.profile"].create({"name": "Proximity Config"})
        self.device = self.env["device.device"].create(
            {
                "name": "Proximity Tracker",
                "identifier": "PROX-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "imei": "TEST-IMEI-PROX-001",
                "device_category_id": self.env.ref("device.device_category_gps").id,
            }
        )
        self.client = self.env["res.partner"].create({"name": "Northern Client"})
        self.parcel = self.env["device.geo.fence"].create(
            {
                "name": "Northern Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": self.client.id,
                "polygon_points": json_dumps(
                    [
                        [NORTHERN_LATITUDE - PARCEL_HALF_SIDE, lon]
                        for lon in (
                            NORTHERN_LONGITUDE - PARCEL_HALF_SIDE,
                            NORTHERN_LONGITUDE + PARCEL_HALF_SIDE,
                        )
                    ]
                    + [
                        [NORTHERN_LATITUDE + PARCEL_HALF_SIDE, lon]
                        for lon in (
                            NORTHERN_LONGITUDE + PARCEL_HALF_SIDE,
                            NORTHERN_LONGITUDE - PARCEL_HALF_SIDE,
                        )
                    ]
                ),
            }
        )
        self.env.flush_all()

    def _place_east_of_the_parcel(self, metres_beyond_the_edge):
        self.env.cr.execute(
            """
            SELECT ST_Y(point), ST_X(point)
              FROM (
                SELECT ST_Project(
                           ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                           ST_Distance(
                               ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                               ST_SetSRID(
                                   ST_MakePoint(%(lon)s + %(half)s, %(lat)s), 4326
                               )::geography
                           ) + %(beyond)s,
                           radians(90)
                       )::geometry AS point
              ) AS projected
            """,
            {
                "lon": NORTHERN_LONGITUDE,
                "lat": NORTHERN_LATITUDE,
                "half": PARCEL_HALF_SIDE,
                "beyond": metres_beyond_the_edge,
            },
        )
        latitude, longitude = self.env.cr.fetchone()
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        self.device.sudo().log_gps_last_id = log.id
        self.env.flush_all()
        self.env.invalidate_all()
        return log

    def _place_on_the_parcel(self):
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": NORTHERN_LATITUDE,
                "longitude": NORTHERN_LONGITUDE,
            }
        )
        self.device.sudo().log_gps_last_id = log.id
        self.env.flush_all()

    def _resolved_parcel(self):
        self.env.invalidate_all(flush=False)
        return self.device.current_client_geofence_id

    def _true_distance_to_the_parcel(self, log):
        self.env.cr.execute(
            """
            SELECT ST_Distance(
                       ST_Transform(f.the_geom, 4326)::geography,
                       l.the_point::geography
                   )
              FROM device_geo_fence f, device_data_log_gps l
             WHERE f.id = %s AND l.id = %s
            """,
            (self.parcel.id, log.id),
        )
        return self.env.cr.fetchone()[0]

    def test_a_device_inside_the_tolerance_resolves_this_far_north(self):
        log = self._place_east_of_the_parcel(48.0)
        distance = self._true_distance_to_the_parcel(log)

        self.assertGreater(distance, 45.0)
        self.assertLess(
            distance,
            50.0,
            "the fixture has to sit in the band where a metre tolerance and a "
            "Web Mercator one disagree; at this latitude the uncorrected 50 "
            "reached only 42.1 m",
        )
        self.assertEqual(self.device.current_client_geofence_id, self.parcel)

    def test_a_device_beyond_the_tolerance_still_does_not_resolve(self):
        log = self._place_east_of_the_parcel(60.0)

        self.assertGreater(self._true_distance_to_the_parcel(log), 50.0)
        self.assertFalse(self.device.current_client_geofence_id)

    def test_archiving_the_parcel_stops_it_resolving(self):
        self._place_on_the_parcel()
        self.assertEqual(self._resolved_parcel(), self.parcel)

        self.parcel.active = False

        self.assertFalse(
            self._resolved_parcel(),
            "the compute reads device_geo_fence with raw SQL, which does not "
            "see the ORM's pending writes; unflushed it read active as still "
            "true and put the vehicle on an archived parcel",
        )

    def test_retyping_the_parcel_stops_it_resolving(self):
        self._place_on_the_parcel()
        self.assertEqual(self._resolved_parcel(), self.parcel)

        self.parcel.area_type = "structure"

        self.assertFalse(
            self._resolved_parcel(),
            "the query filters on area_type, so an unflushed retype left the "
            "vehicle on something that is no longer a parcel",
        )

    def test_a_flushed_transaction_was_always_right(self):
        self._place_on_the_parcel()
        self.parcel.active = False
        self.env.flush_all()

        self.assertFalse(
            self._resolved_parcel(),
            "with the write already in the database there was never anything "
            "wrong here; this is what pins the cause on the missing flush "
            "rather than on the query",
        )
