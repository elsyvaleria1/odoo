import logging
from unittest.mock import patch

from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.geometry import shape as shapely_shape

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import fields as geo_fields
from ..models.fields import (
    _is_foreign_table,
    _parse_geometry,
    _srid_from_crs_member,
    create_geo_index,
    geo_index_name,
    reproject,
)

logger = logging.getLogger(__name__)


class TestGeoFieldConversion(TransactionCase):
    def test_parse_geometry_wkt(self):
        point_wkt = "POINT(10 20)"
        geom = _parse_geometry(point_wkt)
        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "Point")
        self.assertAlmostEqual(geom.x, 10.0)
        self.assertAlmostEqual(geom.y, 20.0)

    def test_parse_geometry_wkt_with_srid(self):
        point_wkt = "SRID=3857;POINT(10 20)"
        geom = _parse_geometry(point_wkt)
        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "Point")
        self.assertAlmostEqual(geom.x, 10.0)
        self.assertAlmostEqual(geom.y, 20.0)

    def test_parse_geometry_linestring(self):
        line_wkt = "LINESTRING(0 0, 10 10, 20 20)"
        geom = _parse_geometry(line_wkt)
        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "LineString")
        self.assertEqual(len(geom.coords), 3)

    def test_parse_geometry_polygon(self):
        polygon_wkt = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
        geom = _parse_geometry(polygon_wkt)
        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "Polygon")

    def test_parse_geometry_empty(self):
        self.assertIsNone(_parse_geometry(None))
        self.assertIsNone(_parse_geometry(""))
        self.assertIsNone(_parse_geometry("  "))

    def test_parse_geometry_invalid(self):
        with self.assertRaises(ValueError):
            _parse_geometry("INVALID GEOMETRY")

        with self.assertRaises(ValueError):
            _parse_geometry("SRID=3857")

    def test_parse_geometry_shapely_object(self):
        point = Point(10, 20)
        result = _parse_geometry(point)
        self.assertIs(result, point)

    def test_parse_geometry_wkb_hex(self):
        point = Point(10, 20)
        wkb_hex = point.wkb_hex

        parsed = _parse_geometry(wkb_hex)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.geom_type, "Point")
        self.assertAlmostEqual(parsed.x, 10.0)
        self.assertAlmostEqual(parsed.y, 20.0)


class TestGeoFieldStorage(TransactionCase):
    def setUp(self):
        super().setUp()

        try:
            self.env.cr.execute("SELECT postgis_version()")
            result = self.env.cr.fetchone()
            if not result:
                self.skipTest("PostGIS not available")
        except Exception:
            self.skipTest("PostGIS not available")

        self.env.cr.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'gps_tracking_log'
            )
            """,
        )
        if not self.env.cr.fetchone()[0]:
            self.skipTest("gps_tracking module not installed")

    def test_geo_point_column_creation(self):
        self.env.cr.execute(
            """
            SELECT column_name, udt_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'gps_tracking_log'
            AND column_name = 'the_point'
            """,
        )
        result = self.env.cr.fetchone()
        self.assertIsNotNone(result, "the_point column should exist")

    def test_geo_point_gist_index(self):
        self.env.cr.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'gps_tracking_log'
            AND indexdef ILIKE '%gist%'
            AND indexdef LIKE '%the_point%'
            """,
        )
        result = self.env.cr.fetchone()
        self.assertIsNotNone(result, "GIST index should exist for the_point")

    def test_geo_point_srid_constraint(self):
        self.env.cr.execute(
            """
            SELECT srid, type
            FROM geometry_columns
            WHERE f_table_name = 'gps_tracking_log'
            AND f_geometry_column = 'the_point'
            """,
        )
        result = self.env.cr.fetchone()
        if result:
            srid, geom_type = result
            self.assertEqual(srid, 3857, "SRID should be 3857 (Web Mercator)")
            self.assertIn("POINT", geom_type.upper(), "Should be POINT type")


class TestGeoIndexForeignTable(TransactionCase):
    def test_is_foreign_table_regular_table(self):
        self.assertFalse(_is_foreign_table(self.env.cr, "res_partner"))
        self.assertFalse(_is_foreign_table(self.env.cr, "no_such_table_xyz"))

    def test_create_geo_index_skips_foreign_table(self):
        # A foreign table cannot be indexed, so the upgrade must warn and go
        # on instead of aborting on CREATE INDEX.
        indexname = geo_index_name("res_partner", "the_point_foreign")
        with (
            patch.object(geo_fields, "_is_foreign_table", return_value=True),
            self.assertLogs("odoo.schema", level="WARNING") as logs,
        ):
            create_geo_index(self.env.cr, "res_partner", "the_point_foreign")
        self.assertIn("foreign table", logs.output[0])
        self.env.cr.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = %s", (indexname,)
        )
        self.assertIsNone(self.env.cr.fetchone())


class TestGeoFieldGeoJSON(TransactionCase):
    def test_point_to_geojson(self):
        point = Point(10, 20)
        geojson_dict = mapping(point)

        self.assertEqual(geojson_dict["type"], "Point")
        self.assertEqual(tuple(geojson_dict["coordinates"]), (10.0, 20.0))

    def test_linestring_to_geojson(self):
        line = LineString([(0, 0), (10, 10), (20, 20)])
        geojson_dict = mapping(line)

        self.assertEqual(geojson_dict["type"], "LineString")
        self.assertEqual(len(geojson_dict["coordinates"]), 3)

    def test_polygon_to_geojson(self):
        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        geojson_dict = mapping(polygon)

        self.assertEqual(geojson_dict["type"], "Polygon")
        self.assertEqual(len(geojson_dict["coordinates"]), 1)
        self.assertEqual(len(geojson_dict["coordinates"][0]), 5)


@tagged("post_install", "-at_install")
class TestCrsMemberReader(TransactionCase):
    def test_every_crs_spelling_reads_as_its_code(self):
        cases = {
            "EPSG:4326": 4326,
            "epsg:3857": 3857,
            "urn:ogc:def:crs:EPSG::4326": 4326,
            "urn:ogc:def:crs:EPSG:6.6:4326": 4326,
            "urn:ogc:def:crs:EPSG:8.9:32614": 32614,
        }
        got = {
            name: _srid_from_crs_member({"properties": {"name": name}})
            for name in cases
        }
        self.assertEqual(got, cases)

    def test_a_crs_that_names_no_epsg_code_declares_nothing(self):
        for name in ("urn:ogc:def:crs:OGC:1.3:CRS84", "", "not a crs"):
            with self.subTest(name=name):
                self.assertIsNone(_srid_from_crs_member({"properties": {"name": name}}))

    def test_the_versioned_urn_survives_a_round_trip(self):
        target = next(
            (
                field
                for field in self.env["ir.model.fields"].search(
                    [("ttype", "=", "geo_point")]
                )
                if field.model in self.env
            ),
            None,
        )
        if not target:
            self.skipTest("no geo_point field installed to write into")
        partner_geo = target
        model = self.env[partner_geo.model]
        field = model._fields[partner_geo.name]
        value = {
            "type": "Point",
            "coordinates": [-99.1332, 19.4326],
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG:6.6:4326"},
            },
        }
        shape = field._normalize_for_storage(value, model.new({}))
        expected = reproject(
            shapely_shape({"type": "Point", "coordinates": [-99.1332, 19.4326]}),
            4326,
            field.srid,
        )
        self.assertAlmostEqual(shape.x, expected.x, delta=1)
        self.assertAlmostEqual(shape.y, expected.y, delta=1)
