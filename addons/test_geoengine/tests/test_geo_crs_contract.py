from shapely import get_srid

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.models.fields import (
    _parse_geometry,
    reproject,
)
from odoo.addons.test_geoengine.models.geo_crs_contract import CrsZone


def _extract_srid(value):
    return get_srid(_parse_geometry(value)) or None


@tagged("post_install", "-at_install", "geoengine_audit")
class TestCrsContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Zone = cls.env[CrsZone._name]

    def test_extract_srid_reads_the_crs_member_this_module_writes(self):
        zone = self.Zone.create(
            {
                "name": "mx",
                "area_mercator": "SRID=4326;POLYGON((-99.2 19.3,-98.9 19.3,-98.9 19.6,-99.2 19.3))",
            }
        )
        served = self.Zone._fields["area_mercator"].convert_to_read(
            zone.area_mercator, zone
        )
        self.assertIn('"crs"', served, "convert_to_read must declare its CRS")
        self.assertEqual(
            _extract_srid(served),
            3857,
            "the crs member convert_to_read writes must be readable by _extract_srid",
        )

    def test_extract_srid_understands_both_epsg_spellings(self):
        for name, expected in (
            ("EPSG:4326", 4326),
            ("urn:ogc:def:crs:EPSG::4326", 4326),
            ("EPSG:6372", 6372),
        ):
            payload = json_dumps(
                {
                    "type": "Point",
                    "coordinates": [0, 0],
                    "crs": {"type": "name", "properties": {"name": name}},
                }
            )
            self.assertEqual(_extract_srid(payload), expected, name)

    def test_extract_srid_returns_none_when_nothing_is_declared(self):
        self.assertIsNone(_extract_srid('{"type": "Point", "coordinates": [0, 0]}'))
        self.assertIsNone(_extract_srid("POINT(0 0)"))

    def test_writing_labelled_geojson_reprojects_to_the_field_srid(self):
        mercator = json_dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-11040000, 2190000],
                        [-11020000, 2190000],
                        [-11020000, 2210000],
                        [-11040000, 2190000],
                    ]
                ],
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            }
        )
        zone = self.Zone.create({"name": "labelled", "area_wgs84": mercator})
        self.env.flush_all()

        minx, miny, maxx, maxy = zone.area_wgs84.bounds
        self.assertTrue(
            -100 < minx < -98 and 18 < miny < 21,
            f"expected WGS84 degrees near Mexico City, stored {zone.area_wgs84.bounds}",
        )
        self.assertTrue(
            abs(maxx) < 180 and abs(maxy) < 90,
            "Web-Mercator metres were stored verbatim as degrees",
        )

    def test_unlabelled_geojson_is_taken_to_be_in_the_field_srid(self):
        plain = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'
        zone = self.Zone.create({"name": "plain", "area_wgs84": plain})
        self.env.flush_all()
        self.assertEqual(zone.area_wgs84.bounds, (0.0, 0.0, 1.0, 1.0))

    def test_a_geometry_survives_a_round_trip_through_the_map(self):
        original = "SRID=4326;POLYGON((-99.2 19.3,-98.9 19.3,-98.9 19.6,-99.2 19.3))"
        for field_name in ("area_wgs84", "area_mercator"):
            with self.subTest(field=field_name):
                first = self.Zone.create({"name": "rt", field_name: original})
                self.env.flush_all()
                served = self.Zone._fields[field_name].convert_to_read(
                    first[field_name], first
                )
                second = self.Zone.create({"name": "rt2", field_name: served})
                self.env.flush_all()
                self.assertTrue(
                    first[field_name].equals_exact(second[field_name], 1e-6),
                    f"{field_name} changed shape on a read/write round trip:\n"
                    f"  {first[field_name].bounds}\n  {second[field_name].bounds}",
                )

    def test_map_draw_into_a_non_mercator_field(self):
        drawn = json_dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [762285.18, 5876767.13],
                        [762298.37, 5876558.82],
                        [762174.95, 5876164.40],
                        [762285.18, 5876767.13],
                    ]
                ],
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            }
        )
        zone = self.Zone.create({"name": "drawn", "area_wgs84": drawn})
        self.env.flush_all()
        minx, miny, _maxx, _maxy = zone.area_wgs84.bounds
        self.assertTrue(
            abs(minx) <= 180 and abs(miny) <= 90,
            f"a drawn geometry stored out-of-range lon/lat: {zone.area_wgs84.bounds}",
        )
        self.assertAlmostEqual(minx, 6.847, places=2)
        self.assertAlmostEqual(miny, 46.591, places=2)

    def test_a_geojson_dict_operand_is_accepted(self):
        self.Zone.create(
            {
                "name": "here",
                "area_wgs84": "SRID=4326;POLYGON((0 0,2 0,2 2,0 0))",
            }
        )
        self.env.flush_all()
        found = self.Zone.search(
            [
                (
                    "area_wgs84",
                    "geo_intersect",
                    {"type": "Point", "coordinates": [0.5, 0.4]},
                )
            ]
        )
        self.assertEqual(found.mapped("name"), ["here"])

    def test_an_operand_that_cannot_hold_a_geometry_raises(self):
        for operand in (12345, object()):
            with self.subTest(operand=type(operand).__name__):
                with self.assertRaises(UserError):
                    self.Zone.search([("area_wgs84", "geo_intersect", operand)])

    def test_parse_geometry_accepts_wkb_bytes(self):
        from shapely.geometry import Point

        self.assertTrue(_parse_geometry(Point(1, 2).wkb).equals(Point(1, 2)))

    def test_writing_an_empty_geometry_reports_it(self):
        with self.assertRaises(UserError):
            self.Zone.create({"name": "empty", "area_wgs84": "POLYGON EMPTY"})

    def test_no_geometry_at_all_stores_null(self):
        for blank in ("", False):
            zone = self.Zone.create({"name": "blank", "area_wgs84": blank})
            self.env.flush_all()
            self.assertFalse(zone.area_wgs84)

    def test_reproject_round_trips(self):
        from shapely.geometry import Point

        point = Point(-99.13, 19.43)
        there = reproject(point, 4326, 3857)
        back = reproject(there, 3857, 4326)
        self.assertAlmostEqual(back.x, point.x, places=6)
        self.assertAlmostEqual(back.y, point.y, places=6)
