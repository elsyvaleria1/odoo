import base64

from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.wkb import loads as wkb_loads

from odoo.exceptions import UserError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import common

from odoo.addons.geoengine.wizards.wizard_base_export_geodata import (
    _geom_to_gpb,
    _geom_to_pyshp_parts,
)
from odoo.addons.geoengine.wizards.wizard_base_import_geodata import (
    _gpb_to_wkb,
    _quote_identifier,
)

SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [948695.5, 6002729.5]},
            "properties": {"name": "Zurich", "population": 400000},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [673508.2, 5863471.4]},
            "properties": {"name": "Geneva", "population": 200000},
        },
    ],
    "crs": {
        "type": "name",
        "properties": {"name": "EPSG:3857"},
    },
}


class TestGeoImportWizard(common.TransactionCase):
    def _make_file(self, data: dict) -> str:
        raw = json_dumps_bytes(data)
        return base64.b64encode(raw).decode("ascii")

    def test_parse_file_valid(self):
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "file_data": self._make_file(SAMPLE_GEOJSON),
                "file_name": "test.geojson",
                "geo_field_id": False,
            }
        )
        data = wizard._read_geojson()
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 2)

    def test_detect_srid_from_crs(self):
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "file_data": self._make_file(SAMPLE_GEOJSON),
                "file_name": "test.geojson",
                "geo_field_id": False,
            }
        )

        srid = wizard._get_srid(SAMPLE_GEOJSON)
        self.assertEqual(srid, 3857)

    def test_detect_srid_default_4326(self):
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "file_data": self._make_file(
                    {"type": "FeatureCollection", "features": []}
                ),
                "file_name": "test.geojson",
                "geo_field_id": False,
            }
        )

        srid = wizard._get_srid({"type": "FeatureCollection", "features": []})
        self.assertEqual(srid, 4326)

    def test_import_no_file_raises(self):
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "geo_field_id": False,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_import_empty_features_raises(self):
        empty = {"type": "FeatureCollection", "features": []}
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "file_data": self._make_file(empty),
                "file_name": "empty.geojson",
                "geo_field_id": False,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_import()


class TestGeoExportWizard(common.TransactionCase):
    def test_export_no_records_raises(self):
        wizard = self.env["wizard.base.export.geodata"].create(
            {
                "model_id": self.env.ref("base.model_res_partner").id,
                "domain": "[('id', '=', -1)]",
                "geo_field_id": False,
                "output_srid": "4326",
            }
        )
        with self.assertRaises(UserError):
            wizard.action_export()


class TestGeomToPyshpParts(common.TransactionCase):
    def test_point(self):
        method, args = _geom_to_pyshp_parts(Point(1, 2))
        self.assertEqual((method, args), ("point", (1, 2)))

    def test_multipoint(self):
        method, args = _geom_to_pyshp_parts(MultiPoint([(1, 2), (3, 4)]))
        self.assertEqual(method, "multipoint")
        self.assertCountEqual(args[0], [(1, 2), (3, 4)])

    def test_linestring_and_multilinestring_share_the_polyline_method(self):
        method, _args = _geom_to_pyshp_parts(LineString([(0, 0), (1, 1)]))
        self.assertEqual(method, "line")
        method, args = _geom_to_pyshp_parts(
            MultiLineString([[(0, 0), (1, 1)], [(2, 2), (3, 3)]])
        )
        self.assertEqual(method, "line")
        self.assertEqual(len(args[0]), 2)

    def test_polygon_exterior_is_reoriented_clockwise(self):
        ccw_square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        self.assertTrue(ccw_square.exterior.is_ccw)

        method, args = _geom_to_pyshp_parts(ccw_square)
        self.assertEqual(method, "poly")
        exterior_ring = Polygon(args[0][0])
        self.assertFalse(
            exterior_ring.exterior.is_ccw,
            "exterior ring must be clockwise for Shapefile, or pyshp files "
            "it as a hole with no exterior",
        )

    def test_polygon_with_hole_keeps_both_rings(self):
        poly = Polygon(
            [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
            holes=[[(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]],
        )
        method, args = _geom_to_pyshp_parts(poly)
        self.assertEqual(method, "poly")
        self.assertEqual(len(args[0]), 2, "exterior + one hole = 2 parts")

    def test_multipolygon_flattens_to_one_parts_list(self):
        mp = MultiPolygon(
            [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
                Polygon([(5, 5), (6, 5), (6, 6), (5, 5)]),
            ]
        )
        method, args = _geom_to_pyshp_parts(mp)
        self.assertEqual(method, "poly")
        self.assertEqual(len(args[0]), 2, "one ring per sub-polygon")

    def test_unsupported_geometry_type_returns_none(self):
        from shapely.geometry import GeometryCollection

        self.assertIsNone(_geom_to_pyshp_parts(GeometryCollection()))


class TestGpbCodec(common.TransactionCase):
    def test_round_trips_point(self):
        geom = Point(1.5, -2.5)
        blob = _geom_to_gpb(geom, 4326)
        wkb_bytes, srid = _gpb_to_wkb(blob)
        self.assertEqual(srid, 4326)
        self.assertTrue(wkb_loads(wkb_bytes).equals(geom))

    def test_round_trips_polygon_with_a_hole(self):
        geom = Polygon(
            [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
            holes=[[(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]],
        )
        blob = _geom_to_gpb(geom, 3857)
        wkb_bytes, srid = _gpb_to_wkb(blob)
        self.assertEqual(srid, 3857)
        rebuilt = wkb_loads(wkb_bytes)
        self.assertEqual(len(rebuilt.interiors), 1)
        self.assertTrue(rebuilt.equals(geom))

    def test_header_layout_matches_a_real_gdal_written_blob(self):
        gdal_blob = bytes.fromhex(
            "47500003e6100000cdcccccccccc58c06666666666c658c0666666666666"
            "3340000000000080334001030000000100000005000000cdcccccccccc58"
            "c066666666666633406666666666c658c066666666666633406666666666"
            "c658c00000000000803340cdcccccccccc58c00000000000803340cdcccc"
            "cccccc58c06666666666663340"
        )
        wkb_bytes, srid = _gpb_to_wkb(gdal_blob)
        self.assertEqual(srid, 4326)
        geom = wkb_loads(wkb_bytes)
        self.assertAlmostEqual(geom.bounds[0], -99.2, places=4)
        self.assertAlmostEqual(geom.bounds[2], -99.1, places=4)

    def test_rejects_a_blob_without_the_gp_magic(self):
        with self.assertRaises(ValueError):
            _gpb_to_wkb(b"\x00\x00\x00\x00garbage")


class TestQuoteIdentifier(common.TransactionCase):
    def test_wraps_in_double_quotes(self):
        self.assertEqual(_quote_identifier("parcels"), '"parcels"')

    def test_escapes_embedded_double_quotes(self):
        self.assertEqual(_quote_identifier('a"b'), '"a""b"')
