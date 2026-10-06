from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.trail_wizard import TrailPosition


@tagged("post_install", "-at_install", "geoengine_audit")
class TestTrailWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Position = cls.env[TrailPosition._name]
        cls.model_id = cls.env["ir.model"]._get_id(cls.Position._name)
        cls.start = datetime(2026, 1, 2, 8, 0, 0)
        cls.devices = cls.env["res.partner"].create(
            [{"name": "Truck A"}, {"name": "Truck B"}]
        )
        cls.Position.create(
            [
                {
                    "name": f"{device.name}-{step}",
                    "moment": cls.start + timedelta(minutes=10 * step),
                    "device_id": device.id,
                    "the_point": (
                        f"SRID=4326;POINT({-99.1 + index + step * 0.01} "
                        f"{19.4 + step * 0.01})"
                    ),
                }
                for index, device in enumerate(cls.devices)
                for step in range(5)
            ]
        )

    def _wizard(self, **overrides):
        vals = {
            "model_id": self.model_id,
            "date_field": "moment",
            "date_from": self.start - timedelta(days=1),
            "date_to": self.start + timedelta(days=1),
            "group_by": "none",
        }
        vals.update(overrides)
        return (
            self.env["wizard.base.view.trail"]
            .with_context(default_trail_model=self.Position._name)
            .create(vals)
        )

    def test_the_model_s_own_datetime_field_is_reachable_from_model_id_alone(self):
        wizard = self.env["wizard.base.view.trail"].create({"model_id": self.model_id})
        domain = wizard._fields["date_field_id"].domain
        self.assertIn("model_id", domain)
        self.assertIn("datetime", domain)

        offered = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.model_id),
                ("ttype", "=", "datetime"),
                ("store", "=", True),
            ]
        )
        self.assertIn("moment", offered.mapped("name"))
        self.assertIn("create_date", offered.mapped("name"))

    def test_picking_the_field_sets_the_technical_name(self):
        moment = self.env["ir.model.fields"].search(
            [("model_id", "=", self.model_id), ("name", "=", "moment")], limit=1
        )
        wizard = self.env["wizard.base.view.trail"].create(
            {"model_id": self.model_id, "date_field_id": moment.id}
        )
        self.assertEqual(wizard.date_field, "moment")

    def test_changing_the_model_clears_a_stale_field(self):
        moment = self.env["ir.model.fields"].search(
            [("model_id", "=", self.model_id), ("name", "=", "moment")], limit=1
        )
        wizard = self.env["wizard.base.view.trail"].create(
            {"model_id": self.model_id, "date_field_id": moment.id}
        )
        wizard.model_id = self.env["ir.model"]._get_id("res.partner")
        wizard._onchange_model_id_resets_date_field()
        self.assertFalse(wizard.date_field_id)
        self.assertEqual(wizard.date_field, "write_date")

    def test_a_single_trail_is_generated_and_stored(self):
        wizard = self._wizard()
        wizard.action_generate_trails()
        self.assertEqual(wizard.trail_count, 1)
        trail = wizard.trail_ids
        self.assertTrue(trail.the_trail, "the trail must carry a geometry")
        self.assertEqual(trail.the_trail.geom_type, "LineString")
        self.assertEqual(trail.record_count, 10)

    def test_grouping_produces_one_trail_per_group(self):
        wizard = self._wizard(group_by="device_id")
        wizard.action_generate_trails()
        self.assertEqual(wizard.trail_count, 2)
        self.assertEqual(sorted(wizard.trail_ids.mapped("record_count")), [5, 5])

    def test_grouped_trails_are_told_apart_by_colour(self):
        wizard = self._wizard(group_by="device_id")
        wizard.action_generate_trails()
        colours = wizard.trail_ids.mapped("trail_color")
        self.assertEqual(
            len(set(colours)), 2, f"expected distinct colours, got {colours}"
        )

    def test_an_ungrouped_trail_keeps_the_chosen_colour(self):
        wizard = self._wizard(trail_color="#ABCDEF")
        wizard.action_generate_trails()
        self.assertEqual(wizard.trail_ids.trail_color, "#ABCDEF")

    def test_the_geometry_lands_in_the_result_field_s_srid(self):
        wizard = self._wizard()
        wizard.action_generate_trails()
        minx, miny, maxx, maxy = wizard.trail_ids.the_trail.bounds
        self.assertTrue(
            -180 <= minx <= 180 and -90 <= miny <= 90,
            f"trail stored outside lon/lat range: {(minx, miny, maxx, maxy)}",
        )

    def test_a_non_datetime_date_field_is_rejected_with_a_user_error(self):
        for field_name in ("name", "device_id", "no_such_field"):
            wizard = self._wizard(date_field=field_name, group_by="day")
            with (
                self.subTest(date_field=field_name),
                self.assertRaises(UserError) as caught,
            ):
                wizard.action_generate_trails()
            self.assertIn("moment", str(caught.exception))

    def test_an_unparseable_filter_is_reported_not_discarded(self):
        wizard = self._wizard(domain="[('nope' 'broken')]")
        with self.assertRaises(UserError):
            wizard.action_generate_trails()

    def test_the_result_map_has_a_layer_to_draw_with(self):
        view = self.env.ref("geoengine.view_geo_trail_result_geoengine")
        self.assertTrue(
            view.vector_layer_ids,
            "wizard.base.view.trail.result has a geoengine view with no vector layer: the "
            "wizard's output map cannot draw anything",
        )
        layer = view.vector_layer_ids[0]
        self.assertEqual(layer.geo_field_id.name, "the_trail")
        validation = self.env[
            "wizard.base.view.trail.result"
        ]._check_geo_view_configuration(view)
        self.assertTrue(validation["valid"], validation["errors"])


@tagged("post_install", "-at_install", "geoengine_audit")
class TestTrailFitsTheGeometryLimit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Position = cls.env[TrailPosition._name]
        cls.start = datetime(2026, 1, 2, 8, 0, 0)
        cls.Position.create(
            [
                {
                    "name": str(step),
                    "moment": cls.start + timedelta(seconds=step),
                    "the_point": (
                        f"SRID=4326;POINT({-99.1 + step * 1e-4} "
                        f"{19.4 + (step % 2) * 1e-7})"
                    ),
                }
                for step in range(400)
            ]
        )

    def _generate(self, max_size):
        self.env["ir.config_parameter"].set_param(
            "geoengine.max_geometry_size", str(max_size)
        )
        wizard = self.env["wizard.base.view.trail"].create(
            {
                "model_id": self.env["ir.model"]._get_id(self.Position._name),
                "date_field": "moment",
                "date_from": self.start - timedelta(days=1),
                "date_to": self.start + timedelta(days=1),
            }
        )
        wizard.action_generate_trails()
        return wizard.trail_ids

    def test_a_trail_over_the_limit_is_simplified_to_fit(self):
        [trail] = self._generate(4000)
        self.assertLess(len(trail.the_trail.coords), 400)
        self.assertLessEqual(len(trail.the_trail.wkt), 4000)
        self.assertEqual(trail.record_count, 400)
        self.assertAlmostEqual(trail.the_trail.coords[0][0], -99.1, delta=1e-9)
        self.assertAlmostEqual(
            trail.the_trail.coords[-1][0], -99.1 + 399e-4, delta=1e-9
        )

    def test_a_trail_under_the_limit_keeps_every_position(self):
        [trail] = self._generate(1_000_000)
        self.assertEqual(len(trail.the_trail.coords), 400)

    def test_a_trail_that_cannot_fit_says_how_to_narrow_it(self):
        with self.assertRaisesRegex(UserError, "Narrow the dates"):
            self._generate(30)
