from pyproj import Geod, Transformer

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.geometry_coercion import (
    CoercionMulti,
    CoercionPoly,
    CoercionPt3857,
    CoercionPt4326,
)


@tagged("post_install", "-at_install")
class TestGeometryCoercion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Poly, cls.Multi, cls.P3857, cls.P4326 = (
            cls.env[CoercionPoly._name],
            cls.env[CoercionMulti._name],
            cls.env[CoercionPt3857._name],
            cls.env[CoercionPt4326._name],
        )

    def test_1_bowtie_into_polygon_field_raises_clearly(self):
        with self.assertRaises(UserError):
            self.Poly.create(
                {"name": "bow", "area": "POLYGON((0 0,10 10,10 0,0 10,0 0))"}
            )
            self.env.flush_all()

    def test_0_unparsable_value_is_a_validation_error(self):
        for bad in ("garbage", "POINT(1)", "SRID=3857", {"type": "Point"}, 42):
            with (
                self.subTest(value=bad),
                self.assertRaises(ValidationError),
                self.env.cr.savepoint(flush=False),
            ):
                self.P3857.create({"name": "bad", "loc": bad})
                self.env.flush_all()

    def test_1_bowtie_into_multipolygon_field_repairs(self):
        rec = self.Multi.create(
            {"name": "bow", "area": "POLYGON((0 0,10 10,10 0,0 10,0 0))"}
        )
        self.env.flush_all()
        self.assertEqual(rec.area.geom_type, "MultiPolygon")
        self.assertEqual(rec.area.area, 50.0)

    def test_2_polygon_promoted_into_multi_field(self):
        rec = self.Multi.create({"name": "p", "area": "POLYGON((0 0,1 0,1 1,0 1,0 0))"})
        self.env.flush_all()
        self.assertEqual(rec.area.geom_type, "MultiPolygon")

    def test_2_single_part_multi_demoted_into_single_field(self):
        rec = self.Poly.create(
            {"name": "m", "area": "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))"}
        )
        self.env.flush_all()
        self.assertEqual(rec.area.geom_type, "Polygon")

    def test_2_multipart_into_single_field_refuses(self):
        with self.assertRaises(UserError) as cm:
            self.Poly.create(
                {
                    "name": "m2",
                    "area": "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)),((5 5,6 5,6 6,5 6,5 5)))",
                }
            )
            self.env.flush_all()
        self.assertIn("2", str(cm.exception))

    def test_2_wrong_family_still_refused(self):
        with self.assertRaises(UserError):
            self.Poly.create({"name": "pt", "area": "POINT(1 1)"})
            self.env.flush_all()

    def test_3_or_domain_now_accepted(self):
        view = self.env["ir.ui.view"].search([("type", "=", "geoengine")], limit=1)
        gf = self.env["ir.model.fields"].search(
            [("model", "=", "coercion.poly"), ("name", "=", "area")], limit=1
        )
        base = {
            "name": "L",
            "view_id": view.id,
            "geo_repr": "basic",
            "geo_field_id": gf.id,
        }
        for label, dom, should_pass in [
            ("OR", "['|', ('val','=',1), ('val','=',2)]", True),
            ("AND", "['&', ('val','=',1), ('val','=',2)]", True),
            ("NOT", "['!', ('val','=',1)]", True),
            ("JUNK", "['bogus_string', ('val','=',1)]", False),
        ]:
            try:
                self.env["geoengine.vector.layer"].create({**base, "model_domain": dom})
                got = True
            except ValidationError:
                got = False
            self.assertEqual(got, should_pass, label)

    def test_4_metres_honoured_on_3857(self):
        t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        g = Geod(ellps="WGS84")
        x0, y0 = t.transform(-99.13, 19.43)
        lon1, lat1, _ = g.fwd(-99.13, 19.43, 90, 10000)
        x1, y1 = t.transform(lon1, lat1)
        a = self.P3857.create({"name": "o", "loc": f"POINT({x0} {y0})"})
        b = self.P3857.create({"name": "far10km", "loc": f"POINT({x1} {y1})"})
        self.env.flush_all()
        dom = [
            (
                "loc",
                "geo_dwithin",
                {"geometry": f"POINT({x0} {y0})", "distance": 10500, "unit": "m"},
            )
        ]
        sql = set(self.P3857.search(dom).ids)
        mem = set((a | b).filtered_domain(dom).ids)
        self.assertIn(b.id, sql, "10km point must be within 10500 m")
        self.assertEqual(sql, mem, "SQL and in-memory must agree")
        dom2 = [
            (
                "loc",
                "geo_dwithin",
                {"geometry": f"POINT({x0} {y0})", "distance": 9500, "unit": "m"},
            )
        ]
        self.assertNotIn(b.id, set(self.P3857.search(dom2).ids))

    def test_4_metres_still_right_on_4326(self):
        g = Geod(ellps="WGS84")
        lon1, lat1, _ = g.fwd(-99.13, 19.43, 90, 10000)
        a = self.P4326.create({"name": "o", "loc": "POINT(-99.13 19.43)"})
        b = self.P4326.create({"name": "far", "loc": f"POINT({lon1} {lat1})"})
        self.env.flush_all()
        dom = [
            (
                "loc",
                "geo_dwithin",
                {"geometry": "POINT(-99.13 19.43)", "distance": 10500, "unit": "m"},
            )
        ]
        sql = set(self.P4326.search(dom).ids)
        mem = set((a | b).filtered_domain(dom).ids)
        self.assertIn(b.id, sql)
        self.assertEqual(sql, mem)

    def test_5_empty_operand_matrix(self):
        self.Poly.create({"name": "x", "area": "POLYGON((0 0,1 0,1 1,0 1,0 0))"})
        self.env.flush_all()
        total = self.Poly.search_count([])
        pgfn = {
            "geo_intersect": "Intersects",
            "geo_contains": "Contains",
            "geo_within": "Within",
            "geo_disjoint": "Disjoint",
            "geo_covers": "Covers",
            "geo_equal": "Equals",
        }
        for op, fn in pgfn.items():
            n = len(self.Poly.search([("area", op, "POLYGON EMPTY")]))
            self.env.cr.execute(
                f"SELECT ST_{fn}(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',3857),"
                " ST_GeomFromText('POLYGON EMPTY',3857))"
            )
            pg = self.env.cr.fetchone()[0]
            self.assertEqual(n == total, bool(pg), f"{op} disagrees with PostGIS")
