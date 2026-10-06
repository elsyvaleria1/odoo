from shapely.geometry import shape as to_shape

from odoo.exceptions import AccessError, UserError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.geometry_edit import EditedFence, SplitParcel


def ring(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def drawn(geo_type, coordinates):
    return json_dumps(
        {
            "type": geo_type,
            "coordinates": coordinates,
            "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
        }
    )


SITE = drawn("MultiPolygon", [[ring(0, 0, 100, 100)]])
TWO_SITES = drawn("MultiPolygon", [[ring(0, 0, 100, 100)], [ring(500, 0, 600, 100)]])


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeometryEdit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Fence = cls.env[EditedFence._name]

    def _edit(self, value, sketch, edit, field="zones"):
        result = self.Fence.get_edited_shape(field, value, sketch, edit)
        payload = json_loads(result)
        self.assertEqual(payload["crs"]["properties"]["name"], "EPSG:3857")
        return to_shape(payload)

    def test_a_separate_area_becomes_another_part(self):
        result = self._edit(
            SITE, drawn("Polygon", [ring(500, 0, 600, 100)]), "add_area"
        )
        self.assertEqual(result.geom_type, "MultiPolygon")
        self.assertEqual(len(result.geoms), 2)
        self.assertAlmostEqual(result.area, 20_000)

    def test_an_overlapping_area_grows_the_part_it_overlaps(self):
        result = self._edit(SITE, drawn("Polygon", [ring(50, 0, 150, 100)]), "add_area")
        self.assertEqual(result.geom_type, "Polygon")
        self.assertAlmostEqual(result.area, 15_000)

    def test_an_area_cut_inside_is_a_hole(self):
        result = self._edit(SITE, drawn("Polygon", [ring(25, 25, 75, 75)]), "cut_area")
        [part] = result.geoms if hasattr(result, "geoms") else [result]
        self.assertEqual(len(part.interiors), 1)
        self.assertAlmostEqual(result.area, 7_500)

    def test_an_area_cut_across_the_edge_trims_it(self):
        result = self._edit(
            SITE, drawn("Polygon", [ring(50, -10, 150, 110)]), "cut_area"
        )
        self.assertAlmostEqual(result.area, 5_000)
        self.assertEqual(len(result.interiors), 0)

    def test_the_part_nearest_the_click_is_removed(self):
        result = self._edit(TWO_SITES, drawn("Point", [520, 40]), "remove_part")
        self.assertEqual(result.geom_type, "Polygon")
        self.assertEqual(result.bounds, (0.0, 0.0, 100.0, 100.0))

    def test_a_line_part_is_removed_like_an_area(self):
        result = self._edit(
            drawn(
                "MultiLineString",
                [[[0, 0], [10, 0]], [[0, 50], [10, 50]], [[0, 90], [10, 90]]],
            ),
            drawn("Point", [5, 48]),
            "remove_part",
            field="route",
        )
        self.assertEqual(result.geom_type, "MultiLineString")
        self.assertEqual(
            sorted(line.coords[0][1] for line in result.geoms), [0.0, 90.0]
        )

    def test_the_result_is_stored_as_the_record_s_shape(self):
        value = self.Fence.get_edited_shape(
            "zones", SITE, drawn("Polygon", [ring(500, 0, 600, 100)]), "add_area"
        )
        fence = self.Fence.create({"name": "two sites", "zones": value})
        self.assertEqual(len(fence.zones.geoms), 2)
        self.assertIsNone(self.Fence.get_geometry_problem("zones", value))

    def test_an_edit_that_would_leave_nothing_is_refused(self):
        with self.assertRaisesRegex(UserError, "single part"):
            self.Fence.get_edited_shape(
                "zones", SITE, drawn("Point", [5, 5]), "remove_part"
            )
        with self.assertRaisesRegex(UserError, "Nothing of the shape"):
            self.Fence.get_edited_shape(
                "zones", SITE, drawn("Polygon", [ring(-10, -10, 110, 110)]), "cut_area"
            )

    def test_only_a_clean_drawn_area_edits_an_area(self):
        bow_tie = [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]]
        with self.assertRaisesRegex(UserError, "crosses itself"):
            self.Fence.get_edited_shape(
                "zones", SITE, drawn("Polygon", bow_tie), "add_area"
            )
        with self.assertRaisesRegex(UserError, "Only an area"):
            self.Fence.get_edited_shape(
                "zones", SITE, drawn("LineString", [[0, 0], [5, 5]]), "add_area"
            )
        with self.assertRaisesRegex(UserError, "Only an area"):
            self.Fence.get_edited_shape(
                "route",
                drawn("MultiLineString", [[[0, 0], [10, 0]]]),
                drawn("Polygon", [ring(0, 0, 5, 5)]),
                "add_area",
            )

    def test_an_unknown_edit_a_non_geometry_field_and_a_non_reader_are_refused(self):
        sketch = drawn("Polygon", [ring(0, 0, 5, 5)])
        with self.assertRaises(ValueError):
            self.Fence.get_edited_shape("zones", SITE, sketch, "explode")
        with self.assertRaises(ValueError):
            self.Fence.get_edited_shape("name", SITE, sketch, "add_area")
        outsider = self.env["res.users"].create(
            {"name": "shape editor", "login": "geoengine_shape_editor"}
        )
        with self.assertRaises(AccessError):
            self.Fence.with_user(outsider).get_edited_shape(
                "zones", SITE, sketch, "add_area"
            )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestShapeSplitAndMerge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel, cls.Fence = (cls.env[SplitParcel._name], cls.env[EditedFence._name])

    def _parcel(self, name, zones):
        return self.Parcel.create({"name": name, "zones": zones})

    def test_a_line_across_a_shape_splits_it_into_records(self):
        parcel = self._parcel("north field", SITE)
        line = drawn("LineString", [[30, -10], [30, 110]])
        action = parcel.action_split_shape("zones", line)
        self.assertEqual(action["tag"], "display_notification")
        self.assertIn("2 records", action["params"]["message"])
        self.assertAlmostEqual(parcel.zones.area, 7_000)
        copy = self.Parcel.search(
            [("id", "!=", parcel.id), ("name", "=", "north field")]
        )
        self.assertEqual(len(copy), 1, "the piece is a copy of the record")
        self.assertAlmostEqual(copy.zones.area, 3_000)

    def test_parts_the_line_does_not_cross_stay_with_the_record(self):
        parcel = self._parcel("two sites", TWO_SITES)
        parcel.action_split_shape("zones", drawn("LineString", [[30, -10], [30, 110]]))
        self.assertEqual(len(parcel.zones.geoms), 2)
        self.assertAlmostEqual(parcel.zones.area, 17_000)

    def test_a_line_that_misses_the_shape_splits_nothing(self):
        parcel = self._parcel("north field", SITE)
        with self.assertRaisesRegex(UserError, "does not cut"):
            parcel.action_split_shape(
                "zones", drawn("LineString", [[300, -10], [300, 110]])
            )
        with self.assertRaisesRegex(UserError, "drawn line"):
            parcel.action_split_shape("zones", drawn("Polygon", [ring(0, 0, 5, 5)]))
        self.assertEqual(self.Parcel.search_count([("name", "=", "north field")]), 1)

    def test_shapes_merge_into_the_first_and_the_others_are_archived(self):
        first = self._parcel("first", SITE)
        second = self._parcel(
            "second", drawn("MultiPolygon", [[ring(100, 0, 200, 100)]])
        )
        third = self._parcel("third", drawn("MultiPolygon", [[ring(500, 0, 600, 100)]]))
        action = (first | second | third).action_merge_shapes("zones")
        self.assertIn("3 shapes", action["params"]["message"])
        self.assertTrue(first.active)
        self.assertFalse(second.active or third.active)
        self.assertAlmostEqual(first.zones.area, 30_000)
        self.assertEqual(len(first.zones.geoms), 2, "touching shapes become one part")

    def test_the_first_selected_record_is_the_one_that_stays(self):
        first = self._parcel("first", SITE)
        second = self._parcel(
            "second", drawn("MultiPolygon", [[ring(100, 0, 200, 100)]])
        )
        self.Parcel.browse([second.id, first.id]).action_merge_shapes("zones")
        self.assertTrue(second.active)
        self.assertFalse(first.active)

    def test_a_merge_needs_two_shapes_and_a_model_that_archives(self):
        first = self._parcel("first", SITE)
        with self.assertRaisesRegex(UserError, "two or more"):
            first.action_merge_shapes("zones")
        fences = self.Fence.create([{"zones": SITE}, {"zones": TWO_SITES}])
        with self.assertRaisesRegex(UserError, "cannot be archived"):
            fences.action_merge_shapes("zones")

    def test_separate_shapes_do_not_merge_into_a_single_polygon_field(self):
        records = self.Parcel.create(
            [
                {"name": "a", "area": drawn("Polygon", [ring(0, 0, 10, 10)])},
                {"name": "b", "area": drawn("Polygon", [ring(50, 0, 60, 10)])},
            ]
        )
        with self.assertRaisesRegex(UserError, "separate Polygon parts"):
            records.action_merge_shapes("area")
