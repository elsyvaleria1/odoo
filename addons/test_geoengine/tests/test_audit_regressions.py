import pathlib
from ast import literal_eval

from psycopg.errors import UndefinedObject
from shapely import make_valid
from shapely.geometry import Polygon

from odoo.exceptions import MissingError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons import geoengine
from odoo.addons.geoengine.models.base import COUNTRY_EXTENTS
from odoo.addons.geoengine.models.fields import create_geo_index
from odoo.addons.geoengine.models.geo_types import parse_extent, parse_resolutions
from odoo.addons.geoengine.models.geoengine_vector_layer import MAX_CLASS_VALUES
from odoo.addons.test_geoengine.models.audit_regressions import (
    AuditArea,
    AuditOther,
    AuditSpot,
)

MODULE_ROOT = pathlib.Path(geoengine.__file__).resolve().parent

ARCH = (
    '<geoengine><field name="spot"/><templates>'
    '<t t-name="info_box"><div>x</div></t></templates></geoengine>'
)


@tagged("post_install", "-at_install")
class TestCountryExtents(TransactionCase):
    def test_every_key_is_a_real_country_code(self):
        present = set(
            self.env["res.country"]
            .search([("code", "in", list(COUNTRY_EXTENTS))])
            .mapped("code")
        )
        self.assertFalse(
            sorted(set(COUNTRY_EXTENTS) - present),
            "COUNTRY_EXTENTS keys with no matching res.country",
        )

    def test_the_company_country_reaches_the_map(self):
        self.env.company.country_id = self.env.ref("base.uk")
        self.env["ir.config_parameter"].sudo().set_param(
            "geoengine.default_map_extent", ""
        )
        self.assertEqual(
            self.env["res.partner"]._get_default_map_extent(),
            COUNTRY_EXTENTS["GB"],
        )


@tagged("post_install", "-at_install")
class TestSpatialIndexOnWrongColumn(TransactionCase):
    @mute_logger("odoo.db.cursor")
    def test_gist_on_a_non_geometry_column_raises(self):
        # jsonb, not varchar: btree_gist (installed by other modules) gives
        # varchar a GIST operator class, and this must fail in every database.
        with self.assertRaises(UndefinedObject), self.env.cr.savepoint():
            create_geo_index(self.env.cr, "ir_ui_view", "arch_db")


@tagged("post_install", "-at_install")
class TestAuditRegressions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot, cls.Other = (cls.env[AuditSpot._name], cls.env[AuditOther._name])
        field_model = cls.env["ir.model.fields"]
        cls.spot_field = field_model.search(
            [("model", "=", "audit.spot"), ("name", "=", "spot")], limit=1
        )
        cls.other_field = field_model.search(
            [("model", "=", "audit.other"), ("name", "=", "spot")], limit=1
        )

    def _view(self, name, **settings):
        view = self.env["ir.ui.view"].create(
            {"name": name, "model": "audit.spot", "type": "geoengine", "arch": ARCH}
        )
        if settings:
            self.env["geoengine.view.settings"].create({"view_id": view.id} | settings)
        self.env["geoengine.raster.layer"].create(
            {"name": f"raster-{name}", "view_id": view.id, "raster_type": "osm"}
        )
        return view

    def _layer(self, view, **vals):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "layer",
                "view_id": view.id,
                "geo_repr": "basic",
                "geo_field_id": self.spot_field.id,
            }
            | vals
        )

    def test_layer_accepts_every_operator_the_orm_does(self):
        view = self._view("domains")
        layer = self._layer(view)
        for domain_text in (
            "[('id', 'any', [('id', '=', 1)])]",
            "[('id', 'not any', [('id', '=', 1)])]",
            "[('id', '=?', False)]",
            "['|', ('id', '=', 1), ('id', '=', 2)]",
            "[('name', 'ilike', 'x')]",
        ):
            with self.subTest(domain=domain_text):
                Domain(literal_eval(domain_text))
                layer.model_domain = domain_text

    def test_layer_still_rejects_what_is_not_a_domain(self):
        view = self._view("bad domains")
        layer = self._layer(view)
        for bad in ("['bogus', ('id', '=', 1)]", "{'a': 1}", "[('id',)]", "nonsense("):
            with self.subTest(domain=bad), self.assertRaises(ValidationError):
                layer.model_domain = bad

    def test_the_extent_is_expressed_in_the_view_projection(self):
        view = self._view(
            "wgs84",
            projection="EPSG:4326",
            default_map_extent=COUNTRY_EXTENTS["MX"],
        )
        self._layer(view)
        payload = self.Spot.get_layers(view.id)
        corners = [float(p) for p in payload["default_map_extent"].split(",")]
        self.assertTrue(
            all(abs(v) <= 180 for v in corners),
            f"an EPSG:4326 view was served {payload['default_map_extent']!r}",
        )
        self.assertAlmostEqual(corners[0], -118.34, delta=0.5)
        self.assertAlmostEqual(corners[1], 14.55, delta=0.5)

    def test_a_web_mercator_view_is_served_the_extent_unchanged(self):
        view = self._view("mercator", default_map_extent=COUNTRY_EXTENTS["MX"])
        self._layer(view)
        payload = self.Spot.get_layers(view.id)
        self.assertEqual(payload["default_map_extent"], COUNTRY_EXTENTS["MX"])

    def test_a_layer_on_a_model_with_no_geoengine_view_is_reported(self):
        view = self._view("cross model")
        self._layer(view, name="cross", geo_field_id=self.other_field.id)
        validation = self.Spot.get_layers(view.id)["validation"]
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any("audit.other" in error for error in validation["errors"]),
            validation["errors"],
        )

    def test_a_cross_model_layer_with_a_view_is_accepted(self):
        self.env["ir.ui.view"].create(
            {
                "name": "other geo",
                "model": "audit.other",
                "type": "geoengine",
                "arch": ARCH.replace('name="spot"', 'name="spot"'),
            }
        )
        view = self._view("cross model ok")
        self._layer(view, name="cross", geo_field_id=self.other_field.id)
        self.assertTrue(self.Spot.get_layers(view.id)["validation"]["valid"])

    def test_get_layers_sends_no_audit_columns_and_no_stored_computes(self):
        view = self._view("payload")
        self._layer(view)
        [layer] = self.Spot.get_layers(view.id)["actives"]
        self.assertFalse(
            set(layer)
            & {
                "create_uid",
                "write_uid",
                "create_date",
                "write_date",
                "nb_class_recommended",
                "model_view_id",
            },
            sorted(layer),
        )

    def test_geo_disjoint_with_an_empty_operand_skips_rows_with_no_geometry(self):
        here = self.Spot.create({"name": "here", "spot": "SRID=3857;POINT(0 0)"})
        nowhere = self.Spot.create({"name": "nowhere"})
        self.env.flush_all()

        matched = self.Spot.search(
            [
                ("id", "in", (here + nowhere).ids),
                ("spot", "geo_disjoint", "POINT EMPTY"),
            ]
        )
        self.assertIn(here, matched)
        self.assertNotIn(nowhere, matched)

    def test_distinct_counting_still_treats_an_unset_integer_as_zero(self):
        view = self._view("counting")
        grade = self.env["ir.model.fields"].search(
            [("model", "=", "audit.spot"), ("name", "=", "grade")], limit=1
        )
        model = self.env["ir.model"].search([("model", "=", "audit.spot")], limit=1)
        layer = self._layer(
            view,
            geo_repr="colored",
            classification="unique",
            attribute_field_id=grade.id,
            model_id=model.id,
        )
        self.Spot.create({"name": "has", "grade": 7})
        self.Spot.create({"name": "none"})
        self.env.flush_all()
        self.assertEqual(layer._count_distinct_values(), 2)


@tagged("post_install", "-at_install")
class TestRendererParity(TransactionCase):
    def test_both_render_strategies_reach_the_legend(self):
        root = MODULE_ROOT / "static/src/geoengine"
        strategies = (root / "renderer/render_strategies.js").read_text("utf-8")
        styling = (root / "renderer/geoengine_renderer_styling.js").read_text("utf-8")

        self.assertIn(
            "initLegend",
            strategies,
            "render_strategies.js never mentions initLegend, so the WebGL path "
            "cannot draw a legend: a classified layer would lose it on crossing "
            "webgl_threshold.",
        )
        self.assertIn(
            "initLegend",
            styling,
            "the Canvas path lost its legend call",
        )

    def test_both_render_strategies_label_through_one_function(self):
        root = MODULE_ROOT / "static/src/geoengine"
        for path in (
            "renderer/geoengine_renderer_styling.js",
            "renderer/webgl_style_converter.js",
            "renderer/render_strategies.js",
        ):
            source = (root / path).read_text("utf-8")
            with self.subTest(path=path):
                self.assertRegex(
                    source,
                    r"labelValueFor|LABEL_STYLE",
                    f"{path} draws or converts labels without going through the "
                    "shared label contract",
                )


@tagged("post_install", "-at_install")
class TestWritePathValidation(TransactionCase):
    BOWTIE = "POLYGON((0 0,2 2,2 0,0 2,0 0))"
    SQUARE = "POLYGON((0 0,1 0,1 1,0 1,0 0))"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Area = cls.env[AuditArea._name]

    def _param(self, key, value):
        self.env["ir.config_parameter"].sudo().set_param(key, value)

    def test_write_of_an_invalid_geometry_is_rejected(self):
        self._param("geoengine.validate_geometry", "True")
        self._param("geoengine.auto_repair_geometry", "False")

        record = self.Area.create({"name": "a", "zone": self.SQUARE})
        self.env.flush_all()

        with self.assertRaises(ValidationError):
            record.write({"zone": self.BOWTIE})
            self.env.flush_all()

    def test_an_invalid_geometry_never_reaches_postgis_through_write(self):
        self._param("geoengine.validate_geometry", "True")
        self._param("geoengine.auto_repair_geometry", "False")

        record = self.Area.create({"name": "a", "zone": self.SQUARE})
        self.env.flush_all()

        with self.assertRaises(ValidationError), self.env.cr.savepoint(flush=False):
            record.write({"zone": self.BOWTIE})
            self.env.flush_all()
        self.env.invalidate_all()

        self.env.cr.execute(
            "SELECT ST_IsValid(zone) FROM audit_area WHERE id = %s", (record.id,)
        )
        self.assertTrue(
            self.env.cr.fetchone()[0],
            "the rejected bowtie must not have replaced the stored square",
        )

    def test_write_honours_the_size_cap(self):
        self._param("geoengine.validate_geometry", "True")
        self._param("geoengine.auto_repair_geometry", "False")
        self._param("geoengine.max_geometry_size", "100")

        record = self.Area.create({"name": "a", "zone": self.SQUARE})
        self.env.flush_all()

        oversized = Polygon(
            [(index * 0.001, (index % 7) * 0.002) for index in range(200)] + [(0, 0)]
        )
        with self.assertRaises(ValidationError):
            record.write({"zone": make_valid(oversized).wkt})
            self.env.flush_all()

    def test_create_still_reports_the_same_rejection(self):
        self._param("geoengine.validate_geometry", "True")
        self._param("geoengine.auto_repair_geometry", "False")

        with self.assertRaises(ValidationError):
            self.Area.create({"name": "a", "zone": self.BOWTIE})
            self.env.flush_all()


@tagged("post_install", "-at_install")
class TestOrdinaryUserCanLoadTheMap(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot, cls.Other = (cls.env[AuditSpot._name], cls.env[AuditOther._name])
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "plain user map",
                "model": "audit.spot",
                "type": "geoengine",
                "arch": ARCH,
            }
        )
        cls.env["geoengine.raster.layer"].create(
            {"name": "osm", "view_id": cls.view.id, "raster_type": "osm"}
        )
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain Internal",
                "login": "geoengine_plain_user",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.env["ir.access"].create(
            {
                "name": "audit.spot read",
                "model_id": cls.env["ir.model"]
                .search([("model", "=", "audit.spot")], limit=1)
                .id,
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
            }
        )

    def test_a_plain_internal_user_gets_the_geoengine_view(self):
        view = self.Spot.with_user(self.plain_user)._get_geo_view()
        self.assertEqual(view.type, "geoengine")
        self.assertEqual(view.model, "audit.spot")

    def test_a_plain_internal_user_gets_the_layers(self):
        layers = self.Spot.with_user(self.plain_user).get_layers()
        self.assertEqual(
            len(layers["backgrounds"]),
            1,
            "the basemap must reach a user who is not a geoengine admin",
        )

    def test_the_view_id_argument_is_still_checked_against_the_model(self):
        other = self.env["ir.ui.view"].create(
            {
                "name": "list",
                "model": "audit.spot",
                "type": "list",
                "arch": '<list><field name="name"/></list>',
            }
        )
        with self.assertRaises(MissingError):
            self.Spot.with_user(self.plain_user)._get_geo_view(other.id)

    def test_class_bounds_resolve_the_target_model_for_a_plain_user(self):
        field = self.env["ir.model.fields"].search(
            [("model", "=", "audit.spot"), ("name", "=", "grade")], limit=1
        )
        layer = self.env["geoengine.vector.layer"].create(
            {
                "name": "graded",
                "view_id": self.view.id,
                "geo_repr": "colored",
                "geo_field_id": self.env["ir.model.fields"]
                .search([("model", "=", "audit.spot"), ("name", "=", "spot")], limit=1)
                .id,
                "attribute_field_id": field.id,
                "nb_class": 2,
            }
        )
        self.Spot.create({"name": "a", "grade": 1, "spot": "POINT(0 0)"})
        self.Spot.create({"name": "b", "grade": 9, "spot": "POINT(1 1)"})
        self.env.flush_all()

        bounds = layer.with_user(self.plain_user).get_class_bounds()
        self.assertEqual(bounds, {"min": 1, "max": 9})

    def _cross_model_layer(self):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "cross",
                "view_id": self.view.id,
                "geo_repr": "basic",
                "geo_field_id": self.env["ir.model.fields"]
                .search([("model", "=", "audit.other"), ("name", "=", "spot")], limit=1)
                .id,
            }
        )

    def test_a_cross_model_layer_does_not_deny_the_map_to_a_plain_user(self):
        layer = self._cross_model_layer()
        self.assertEqual(layer.model_id.model, "audit.other")

        payload = self.Spot.with_user(self.plain_user).get_layers(self.view.id)

        self.assertFalse(payload["validation"]["valid"])
        self.assertTrue(
            any("audit.other" in error for error in payload["validation"]["errors"]),
            payload["validation"]["errors"],
        )

    def test_a_plain_user_can_read_model_view_id(self):
        other_view = self.env["ir.ui.view"].create(
            {
                "name": "other geo",
                "model": "audit.other",
                "type": "geoengine",
                "arch": ARCH,
            }
        )
        layer = self._cross_model_layer()
        self.env.flush_all()
        self.assertEqual(layer.model_view_id, other_view)

        read = layer.with_user(self.plain_user).read(["model_view_id"])

        self.assertEqual(
            read[0]["model_view_id"],
            False,
            "the compute must resolve without AccessError; the value is masked "
            "because the user may not read ir.ui.view, which is what an "
            "unreadable many2one is supposed to do",
        )


@tagged("post_install", "-at_install")
class TestClassValuesLimitIsCapped(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot = cls.env[AuditSpot._name]
        view = cls.env["ir.ui.view"].create(
            {"name": "grades", "model": "audit.spot", "type": "geoengine", "arch": ARCH}
        )
        cls.env["geoengine.raster.layer"].create(
            {"name": "osm", "view_id": view.id, "raster_type": "osm"}
        )
        field_model = cls.env["ir.model.fields"]
        cls.layer = cls.env["geoengine.vector.layer"].create(
            {
                "name": "graded",
                "view_id": view.id,
                "geo_repr": "colored",
                "classification": "quantile",
                "nb_class": 2,
                "geo_field_id": field_model.search(
                    [("model", "=", "audit.spot"), ("name", "=", "spot")], limit=1
                ).id,
                "attribute_field_id": field_model.search(
                    [("model", "=", "audit.spot"), ("name", "=", "grade")], limit=1
                ).id,
            }
        )
        for index in range(5):
            cls.Spot.create(
                {"name": f"s{index}", "spot": f"POINT({index} 0)", "grade": index}
            )
        cls.env.flush_all()

    def test_a_caller_cannot_raise_the_limit_past_the_cap(self):
        self.assertEqual(
            self.layer.get_class_values(limit=10**9),
            self.layer.get_class_values(limit=MAX_CLASS_VALUES),
        )

    def test_a_caller_can_still_lower_the_limit(self):
        self.assertEqual(
            self.layer.get_class_values(limit=2),
            [],
            "over the requested limit the layer classifies the drawn features",
        )

    def test_zero_is_read_as_the_cap_not_as_no_values(self):
        self.assertEqual(len(self.layer.get_class_values(limit=0)), 5)


@tagged("post_install", "-at_install")
class TestActiveIdsDomainIsNotReapplied(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot = cls.env[AuditSpot._name]
        view = cls.env["ir.ui.view"].create(
            {"name": "active", "model": "audit.spot", "type": "geoengine", "arch": ARCH}
        )
        cls.env["geoengine.raster.layer"].create(
            {"name": "osm", "view_id": view.id, "raster_type": "osm"}
        )
        field_model = cls.env["ir.model.fields"]
        cls.layer = cls.env["geoengine.vector.layer"].create(
            {
                "name": "by grade",
                "view_id": view.id,
                "geo_repr": "colored",
                "nb_class": 2,
                "geo_field_id": field_model.search(
                    [("model", "=", "audit.spot"), ("name", "=", "spot")], limit=1
                ).id,
                "attribute_field_id": field_model.search(
                    [("model", "=", "audit.spot"), ("name", "=", "grade")], limit=1
                ).id,
            }
        )
        cls.spots = cls.env["audit.spot"]
        for index in range(5):
            cls.spots |= cls.Spot.create(
                {"name": f"s{index}", "spot": f"POINT({index} 0)", "grade": index}
            )
        cls.env.flush_all()

    def test_the_placeholder_is_accepted_as_a_domain(self):
        self.layer.model_domain = '[("id", "in", "{ACTIVE_IDS}")]'
        self.layer.flush_recordset()

    def test_the_placeholder_does_not_empty_the_population(self):
        self.layer.model_domain = '[("id", "in", "{ACTIVE_IDS}")]'
        self.layer.flush_recordset()
        self.assertEqual(self.layer._parsed_model_domain(), [])
        self.assertEqual(self.layer.get_class_bounds(), {"min": 0, "max": 4})
        self.assertEqual(self.layer._count_distinct_values(), 5)

    def test_a_placeholder_nested_in_a_dict_operand_is_detected_too(self):
        self.layer.model_domain = (
            '[("spot", "geo_intersect",'
            ' {"audit.spot.spot": [("id", "in", "{ACTIVE_IDS}")]})]'
        )
        self.layer.flush_recordset()

        self.assertEqual(
            self.layer._parsed_model_domain(),
            [],
            "the placeholder must be detected inside a dict operand's sub-domain: "
            "that is the only shape any layer in the tree actually uses, and left "
            "unresolved it collapses the whole classification to Domain(False)",
        )
        drawn = self.spots[:2].ids
        self.assertEqual(
            self.layer.get_class_bounds([("id", "in", drawn)]),
            {"min": 0, "max": 1},
        )

    def test_the_client_evaluated_domain_is_honoured_verbatim(self):
        self.layer.model_domain = '[("id", "in", "{ACTIVE_IDS}")]'
        self.layer.flush_recordset()
        drawn = self.spots[:2].ids
        self.assertEqual(
            self.layer.get_class_bounds([("id", "in", drawn)]),
            {"min": 0, "max": 1},
            "the expanded domain the client sends must select the drawn subset",
        )
        self.assertEqual(
            sorted(self.layer.get_class_values([("id", "in", drawn)])), [0, 1]
        )

    def test_a_static_model_domain_still_applies_without_extra_domain(self):
        self.layer.model_domain = "[('grade', '>=', 3)]"
        self.layer.flush_recordset()
        self.assertEqual(self.layer.get_class_bounds(), {"min": 3, "max": 4})
        self.assertEqual(self.layer._count_distinct_values(), 2)


@tagged("post_install", "-at_install")
class TestGeometryCollectionCoercion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Area = cls.env[AuditArea._name]

    def _stored(self, record):
        self.env.cr.execute(
            "SELECT ST_GeometryType(zones), ST_NumGeometries(zones) "
            "FROM audit_area WHERE id = %s",
            (record.id,),
        )
        return self.env.cr.fetchone()

    def test_a_multi_member_first_is_flattened(self):
        record = self.Area.create(
            {
                "name": "mp first",
                "zones": "GEOMETRYCOLLECTION("
                "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0))),"
                "POLYGON((5 5,6 5,6 6,5 6,5 5)))",
            }
        )
        self.env.flush_all()
        self.assertEqual(self._stored(record), ("ST_MultiPolygon", 2))

    def test_a_multi_member_last_is_flattened(self):
        record = self.Area.create(
            {
                "name": "mp last",
                "zones": "GEOMETRYCOLLECTION("
                "POLYGON((5 5,6 5,6 6,5 6,5 5)),"
                "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0))))",
            }
        )
        self.env.flush_all()
        self.assertEqual(self._stored(record), ("ST_MultiPolygon", 2))

    def test_several_multi_members_are_all_flattened(self):
        record = self.Area.create(
            {
                "name": "two mps",
                "zones": "GEOMETRYCOLLECTION("
                "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)),((2 2,3 2,3 3,2 3,2 2))),"
                "MULTIPOLYGON(((5 5,6 5,6 6,5 6,5 5))))",
            }
        )
        self.env.flush_all()
        self.assertEqual(self._stored(record), ("ST_MultiPolygon", 3))

    def test_single_members_still_work(self):
        record = self.Area.create(
            {
                "name": "singles",
                "zones": "GEOMETRYCOLLECTION("
                "POLYGON((0 0,1 0,1 1,0 1,0 0)),"
                "POLYGON((5 5,6 5,6 6,5 6,5 5)))",
            }
        )
        self.env.flush_all()
        self.assertEqual(self._stored(record), ("ST_MultiPolygon", 2))

    def test_a_collection_with_nothing_of_the_wanted_type_is_reported(self):
        with self.assertRaises(UserError):
            self.Area.create(
                {
                    "name": "no polygons",
                    "zones": "GEOMETRYCOLLECTION(POINT(0 0),LINESTRING(0 0,1 1))",
                }
            )
            self.env.flush_all()


@tagged("post_install", "-at_install")
class TestWebglTrailFlagMatchesTheClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot = cls.env[AuditSpot._name]

    def _postprocess(self, attrs):
        view = self.env["ir.ui.view"].create(
            {
                "name": "trail flag",
                "model": "audit.spot",
                "type": "geoengine",
                "arch": ARCH.replace("<geoengine>", f"<geoengine {attrs}>"),
            }
        )
        self.env["audit.spot"].get_views([[view.id, "geoengine"]])

    def test_every_truthy_spelling_triggers_the_validation(self):
        for attrs in (
            'webgl_trail="True"',
            'webgl_trail="1"',
            'webgl_trail="true"',
        ):
            with self.subTest(attrs=attrs), self.assertRaises(ValidationError) as ctx:
                self._postprocess(attrs)
            self.assertIn("trail_timestamps_field", str(ctx.exception))

    def test_every_falsy_spelling_leaves_the_view_alone(self):
        for attrs in (
            'webgl_trail="False"',
            'webgl_trail="false"',
            'webgl_trail="0"',
        ):
            with self.subTest(attrs=attrs):
                self._postprocess(attrs)

    def test_a_spelling_outside_the_bool_literals_is_refused(self):
        for attrs in (
            'webgl_trail="TRUE"',
            'webgl_trail="None"',
            'webgl_trail="yes"',
            'webgl_trail=""',
        ):
            with self.subTest(attrs=attrs), self.assertRaises(ValidationError) as ctx:
                self._postprocess(attrs)
            self.assertNotIn("trail_timestamps_field", str(ctx.exception))

    def test_the_attribute_is_optional(self):
        self._postprocess("")


@tagged("post_install", "-at_install")
class TestMapGeometrySettingsAreValidated(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Spot = cls.env[AuditSpot._name]
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "extents",
                "model": "audit.spot",
                "type": "geoengine",
                "arch": ARCH,
            }
        )

    def _raster(self, **vals):
        return self.env["geoengine.raster.layer"].create(
            {"name": "osm", "view_id": self.view.id, "raster_type": "osm"} | vals
        )

    def test_the_shared_parser_agrees_on_what_an_extent_is(self):
        self.assertEqual(parse_extent("1, 2, 3, 4"), (1.0, 2.0, 3.0, 4.0))
        self.assertIsNone(parse_extent("1,2,3"))
        self.assertIsNone(parse_extent("a,b,c,d"))
        self.assertIsNone(parse_extent("4,4,1,1"))
        self.assertIsNone(parse_extent(""))

    def test_the_shared_parser_agrees_on_what_resolutions_are(self):
        self.assertEqual(parse_resolutions("156543.03, 78271.5"), [156543.03, 78271.5])
        self.assertIsNone(parse_resolutions("???"))
        self.assertIsNone(parse_resolutions("156543.03, -1"))
        self.assertIsNone(parse_resolutions("156543.03, 0"))

    def test_resolutions_must_really_be_largest_first(self):
        for unordered in ("1,100,10", "1,2,3", "10,10"):
            with self.subTest(resolutions=unordered):
                self.assertIsNone(
                    parse_resolutions(unordered),
                    "the constraint message promises 'largest first', and "
                    "ol.tilegrid.WMTS throws on anything else — which the "
                    "renderer swallows into a silent OpenStreetMap fallback",
                )
        self.assertEqual(parse_resolutions("100,10,1"), [100.0, 10.0, 1.0])

    def test_unordered_raster_resolutions_are_refused(self):
        with self.assertRaises(ValidationError):
            self._raster(resolutions="1, 100, 10")

    def test_a_malformed_system_extent_is_refused(self):
        settings = self.env["res.config.settings"].create({})
        with self.assertRaises(ValidationError):
            settings.geoengine_map_extent = "1,2,3"
            settings._check_geoengine_map_extent()

    def test_a_well_formed_system_extent_is_accepted(self):
        settings = self.env["res.config.settings"].create({})
        settings.geoengine_map_extent = "-13173896.5, 1632778.9, -9633272.7, 3910375.8"
        settings._check_geoengine_map_extent()

    def test_a_malformed_raster_max_extent_is_refused(self):
        with self.assertRaises(ValidationError):
            self._raster(max_extent="not, a, number, at all")

    def test_malformed_raster_resolutions_are_refused(self):
        with self.assertRaises(ValidationError):
            self._raster(resolutions="???")

    def test_well_formed_raster_geometry_is_accepted(self):
        layer = self._raster(
            max_extent="-20037508, -20037508, 20037508, 20037508",
            resolutions="156543.03, 78271.5, 39135.75",
        )
        self.assertTrue(layer.id)

    def test_a_malformed_extent_is_not_reprojected_silently(self):
        with self.assertLogs(
            "odoo.addons.geoengine.models.base", level="WARNING"
        ) as logs:
            self.assertEqual(
                self.Spot._extent_in_projection("1,2,3", "EPSG:4326"), "1,2,3"
            )
        self.assertIn("malformed map extent", "\n".join(logs.output))

    def test_an_unusable_projection_is_not_swallowed_silently(self):
        with self.assertLogs(
            "odoo.addons.geoengine.models.base", level="WARNING"
        ) as logs:
            self.assertEqual(
                self.Spot._extent_in_projection("1,2,3,4", "banana"), "1,2,3,4"
            )
        self.assertIn("unusable map projection", "\n".join(logs.output))
