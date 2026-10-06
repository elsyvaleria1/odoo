from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGeofenceValidation(TransactionCase):
    def _make_polygon(self, points_json: str):
        return self.env["device.geo.fence"].create(
            {
                "name": "Validation Test Fence",
                "geofence_type": "polygon",
                "polygon_points": points_json,
            }
        )

    def test_geometry_keeps_its_projection_across_a_type_only_write(self) -> None:
        fence = self.env["device.geo.fence"].create(
            {
                "name": "circle",
                "geofence_type": "circle",
                "center_latitude": 19.43,
                "center_longitude": -99.13,
                "radius": 500,
            }
        )
        fence.write(
            {
                "geofence_type": "polygon",
                "polygon_points": "[[19.4,-99.2],[19.5,-99.2],[19.5,-99.1],[19.4,-99.1]]",
            }
        )
        fence.write({"geofence_type": "circle"})
        fence.flush_recordset()
        self.env.cr.execute(
            "SELECT ST_SRID(the_geom), ST_X(ST_Centroid(the_geom)) "
            "FROM device_geo_fence WHERE id = %s",
            (fence.id,),
        )
        srid, centroid_x = self.env.cr.fetchone()
        self.assertEqual(srid, 3857)
        self.assertLess(centroid_x, -11_000_000)

    def test_surface_follows_the_polygon_on_create_and_write(self) -> None:
        fence = self._make_polygon(
            "[[19.4,-99.2],[19.5,-99.2],[19.5,-99.1],[19.4,-99.1]]"
        )
        small = fence.surface
        self.assertGreater(small, 0.0)
        fence.write(
            {"polygon_points": "[[19.4,-99.2],[19.6,-99.2],[19.6,-99.0],[19.4,-99.0]]"}
        )
        self.assertAlmostEqual(fence.surface / small, 4.0, delta=0.05)

    def test_valid_polygon_accepted(self) -> None:
        fence = self._make_polygon("[[19.4, -99.1], [19.5, -99.2], [19.6, -99.0]]")
        self.assertTrue(fence.exists())

    def test_non_numeric_point_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self._make_polygon('[["x", 1], [19.5, -99.2], [19.6, -99.0]]')

    def test_out_of_range_point_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self._make_polygon("[[91.0, -99.1], [19.5, -99.2], [19.6, -99.0]]")

    def test_wrong_arity_point_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self._make_polygon("[[19.4], [19.5, -99.2], [19.6, -99.0]]")
