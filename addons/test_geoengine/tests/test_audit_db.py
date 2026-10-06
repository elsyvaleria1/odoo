import base64

from shapely.geometry import LineString, Polygon

from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.audit_db import GeoAuditFixture


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeoengineAuditDB(TransactionCase):
    MODEL_NAME = "geoengine.audit.fixture"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Fixture = cls.env[GeoAuditFixture._name]

    def _stored_point(self, rec):
        self.env.cr.execute(
            "SELECT ST_SRID(the_point), ST_X(the_point), ST_Y(the_point) "
            "FROM geoengine_audit_fixture WHERE id = %s",
            (rec.id,),
        )
        return self.env.cr.fetchone()

    def _column_srid(self, column):
        self.env.cr.execute(
            "SELECT srid FROM geometry_columns "
            "WHERE f_table_name = %s AND f_geometry_column = %s",
            ("geoengine_audit_fixture", column),
        )
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def test_spatial_search_intersect_baseline(self):
        inside = self.Fixture.create(
            {"name": "in", "the_point": "SRID=3857;POINT(50 50)"}
        )
        outside = self.Fixture.create(
            {"name": "out", "the_point": "SRID=3857;POINT(5000 5000)"}
        )
        self.Fixture.flush_model()
        box = Polygon([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
        found = self.Fixture.search([("the_point", "geo_intersect", box)])
        self.assertIn(inside, found)
        self.assertNotIn(outside, found)

    def test_input_srid_is_ignored_no_reprojection(self):
        rec = self.Fixture.create(
            {"name": "paris", "the_point": "SRID=4326;POINT(2.3522 48.8566)"}
        )
        self.Fixture.flush_model()
        srid, px, py = self._stored_point(rec)
        self.assertEqual(srid, 3857)
        self.assertAlmostEqual(
            px,
            261848.15,
            delta=5000,
            msg=f"the_point was not reprojected 4326->3857: stored x={px} "
            f"(expected ~261848; verbatim-unreprojected value would be ~2.35)",
        )
        self.assertAlmostEqual(
            py,
            6250566.0,
            delta=5000,
            msg=f"the_point was not reprojected 4326->3857: stored y={py} "
            f"(expected ~6250566; verbatim-unreprojected value would be ~48.86)",
        )

    def test_geo_extent_aggregate_breaks_geojson_contract(self):
        self.Fixture.create(
            [
                {"name": "a", "the_point": "SRID=3857;POINT(0 0)"},
                {"name": "b", "the_point": "SRID=3857;POINT(100 200)"},
            ]
        )
        self.Fixture.flush_model()
        extent = self.Fixture._read_group([], [], ["the_point:geo_extent"])[0][0]
        union = self.Fixture._read_group([], [], ["the_point:geo_union"])[0][0]
        self.assertIsInstance(json_loads(union), dict, "geo_union should be GeoJSON")
        self.assertNotIn(
            "BOX",
            str(extent),
            msg=f"geo_extent returned a PostGIS BOX literal, not GeoJSON: {extent!r}",
        )
        self.assertIsInstance(
            json_loads(extent), dict, "geo_extent should be parseable GeoJSON"
        )

    def test_wrong_type_geometry_raises_clean_error_not_attributeerror(self):
        try:
            self.Fixture.create(
                {"name": "bad", "the_point": "SRID=3857;LINESTRING(0 0, 1 1)"}
            )
            self.Fixture.flush_model()
            self.fail("Expected an error writing a LineString into a GeoPoint field")
        except AssertionError:
            raise
        except Exception as exc:
            self.assertNotIsInstance(
                exc,
                AttributeError,
                msg=f"Got AttributeError instead of a clean geometry-type error: {exc!r}",
            )
            self.assertIn("mismatch", str(exc).lower())

    def test_geofield_accepts_geojson_from_map_editor(self):
        rec = self.Fixture.create(
            {"name": "drawn", "the_point": '{"type":"Point","coordinates":[100,200]}'}
        )
        self.Fixture.flush_model()
        srid, px, py = self._stored_point(rec)
        self.assertEqual(srid, 3857)
        self.assertAlmostEqual(px, 100, delta=0.01)
        self.assertAlmostEqual(py, 200, delta=0.01)

    def test_srid_change_migrates_column_so_writes_succeed(self):
        field = self.Fixture._fields["the_point"]
        self.assertEqual(self._column_srid("the_point"), 3857)
        self.addCleanup(setattr, field, "srid", field.srid)

        field.srid = 4326
        field.update_db_column(self.Fixture, {"udt_name": "geometry"})
        col_srid = self._column_srid("the_point")

        write_error = None
        try:
            with self.env.cr.savepoint():
                self.Fixture.create(
                    {"name": "x", "the_point": "SRID=4326;POINT(2.35 48.85)"}
                )
                self.Fixture.flush_model()
        except Exception as exc:
            write_error = exc

        self.assertEqual(
            col_srid,
            4326,
            msg=f"update_db_column left the column at SRID {col_srid} after the field "
            f"changed to 4326 (silent 'Continuing anyway'); write_error={write_error}",
        )
        self.assertIsNone(
            write_error,
            msg=f"write failed after SRID change because the column was not migrated: "
            f"{write_error}",
        )

    def test_domain_optimizer_reprojects_query_geometry(self):
        paris = self.Fixture.create(
            {"name": "paris", "the_point": "SRID=3857;POINT(261848 6250566)"}
        )
        self.Fixture.flush_model()
        box_4326 = (
            "SRID=4326;POLYGON((2.0 48.5, 2.7 48.5, 2.7 49.0, 2.0 49.0, 2.0 48.5))"
        )
        found = self.Fixture.search([("the_point", "geo_intersect", box_4326)])
        self.assertIn(
            paris,
            found,
            msg="the geo domain optimizer did not reproject the 4326 query box to "
            "the 3857 field; the spatial filter silently matched nothing",
        )

    def test_export_wizard_reprojects_to_output_srid(self):
        rec = self.Fixture.create(
            {"name": "paris", "the_point": "SRID=3857;POINT(261848 6250566)"}
        )
        self.Fixture.flush_model()
        wizard = self.env["wizard.base.export.geodata"].create(
            {
                "model_id": self.env["ir.model"]._get_id(self.MODEL_NAME),
                "geo_field_id": self.env["ir.model.fields"]
                ._get(self.MODEL_NAME, "the_point")
                .id,
                "domain": f"[('id', '=', {rec.id})]",
                "output_srid": "4326",
            }
        )
        wizard.action_export()
        [feature] = json_loads(base64.b64decode(wizard.output_file))["features"]
        lon, lat = feature["geometry"]["coordinates"]
        self.assertAlmostEqual(
            lon, 2.3522, delta=0.01, msg=f"exporter did not reproject: lon={lon}"
        )
        self.assertAlmostEqual(
            lat, 48.8566, delta=0.01, msg=f"exporter did not reproject: lat={lat}"
        )

    def test_trail_wizard_reprojects_source_to_wgs84(self):
        ir_model = self.env["ir.model"].search([("model", "=", "res.partner")], limit=1)
        wizard = self.env["wizard.base.view.trail"].create({"model_id": ir_model.id})
        trail = {
            "name": "paris-trail",
            "geometry": LineString([(261848, 6250566), (300000, 6300000)]),
            "record_count": 2,
        }
        results = wizard._store_trail_results([trail], source_srid=3857)
        self.env.cr.execute(
            "SELECT ST_SRID(the_trail), ST_X(ST_StartPoint(the_trail)), "
            "ST_Y(ST_StartPoint(the_trail)) FROM wizard_base_view_trail_result WHERE id = %s",
            (results.id,),
        )
        srid, px, py = self.env.cr.fetchone()
        self.assertEqual(srid, 4326)
        self.assertAlmostEqual(
            px, 2.3522, delta=0.05, msg=f"trail start not reprojected: x={px}"
        )
        self.assertAlmostEqual(
            py, 48.8566, delta=0.05, msg=f"trail start not reprojected: y={py}"
        )
