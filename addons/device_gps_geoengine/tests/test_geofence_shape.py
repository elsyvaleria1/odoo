from shapely.geometry import MultiPolygon, Polygon

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import common, tagged

from odoo.addons.geoengine.models.fields import shape_to_geojson

YARD = [[19.39, -99.11], [19.41, -99.11], [19.41, -99.09], [19.39, -99.09]]


def lonlat_ring(points):
    return [(lon, lat) for lat, lon in points]


def area(*polygons):
    return shape_to_geojson(MultiPolygon(list(polygons)), 4326)


@tagged("post_install", "-at_install")
class TestGeofenceShape(common.TransactionCase):
    def _fence(self, **values):
        return self.env["device.geo.fence"].create(
            {"name": "Yard", "geofence_type": "polygon", **values}
        )

    def _points(self, fence):
        return json_loads(fence.polygon_points)

    def test_points_written_by_the_form_or_api_become_the_shape(self):
        fence = self._fence(polygon_points=json_dumps(YARD))
        self.assertEqual(self._points(fence), YARD)
        self.assertTrue(fence.the_geom)
        self.assertTrue(fence._is_point_inside(19.40, -99.10))
        self.assertFalse(fence._is_point_inside(19.50, -99.10))

    def test_a_shape_drawn_on_the_map_gives_the_points(self):
        fence = self._fence(the_geom=area(Polygon(lonlat_ring(YARD))))
        self.assertEqual(self._points(fence), YARD)
        self.assertGreater(fence.surface, 0)

    def test_containment_follows_a_reshape_on_the_map(self):
        fence = self._fence(polygon_points=json_dumps(YARD))
        self.assertTrue(fence._is_point_inside(19.40, -99.10))
        moved = [[lat + 0.1, lon] for lat, lon in YARD]
        surface = fence.surface
        fence.the_geom = area(Polygon(lonlat_ring(moved)))
        self.assertFalse(
            fence._is_point_inside(19.40, -99.10),
            "alerts still tested the polygon the map no longer shows",
        )
        self.assertTrue(fence._is_point_inside(19.50, -99.10))
        self.assertEqual(
            self._points(fence), [[round(lat, 7), lon] for lat, lon in moved]
        )
        self.assertAlmostEqual(fence.surface, surface, delta=surface * 0.01)

    def test_a_hole_and_a_second_area_count(self):
        hole = [
            (-99.105, 19.395),
            (-99.095, 19.395),
            (-99.095, 19.405),
            (-99.105, 19.405),
        ]
        second = Polygon(
            lonlat_ring([[19.60, -99.11], [19.62, -99.11], [19.62, -99.09]])
        )
        fence = self._fence(the_geom=area(Polygon(lonlat_ring(YARD), [hole]), second))
        self.assertFalse(fence._is_point_inside(19.40, -99.10), "inside the hole")
        self.assertTrue(
            fence._is_point_inside(19.391, -99.109), "between hole and edge"
        )
        self.assertTrue(fence._is_point_inside(19.615, -99.105), "in the second area")
        self.assertEqual(self._points(fence), YARD, "the points are the first outline")

    def test_a_circle_is_drawn_from_its_centre_and_radius(self):
        fence = self._fence(
            geofence_type="circle",
            center_latitude=19.40,
            center_longitude=-99.10,
            radius=500,
        )
        self.assertTrue(fence.the_geom)
        self.assertFalse(fence.polygon_points)
        small = fence.surface
        fence.radius = 1000
        self.assertAlmostEqual(fence.surface, small * 4, delta=small * 0.1)
        self.assertTrue(fence._is_point_inside(19.40, -99.10))

    def test_split_and_merge_on_the_map_keep_fences_whole(self):
        fence = self._fence(polygon_points=json_dumps(YARD))
        surface = fence.surface
        line = json_dumps(
            {
                "type": "LineString",
                "coordinates": [[-99.10, 19.38], [-99.10, 19.42]],
                "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            }
        )
        fence.action_split_shape("the_geom", line)
        pieces = self.env["device.geo.fence"].search([("name", "=", "Yard")])
        self.assertEqual(len(pieces), 2)
        self.assertEqual(
            sorted(piece._is_point_inside(19.40, -99.105) for piece in pieces),
            [False, True],
            "each half holds its own side",
        )
        pieces.action_merge_shapes("the_geom")
        self.assertEqual(len(pieces.filtered("active")), 1)
        merged = pieces.filtered("active")
        self.assertTrue(merged._is_point_inside(19.40, -99.105))
        self.assertTrue(merged._is_point_inside(19.40, -99.095))
        self.assertAlmostEqual(merged.surface, surface, delta=surface * 1e-6)

    def test_the_geofence_map_offers_editing(self):
        view = self.env.ref("device_gps_geoengine.view_device_geo_fence_map")
        arch = self.env["device.geo.fence"].get_views([(view.id, "geoengine")])[
            "views"
        ]["geoengine"]["arch"]
        self.assertIn('editable="1"', arch)
