from odoo.exceptions import AccessError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.test_geoengine.models.geometry_check import CheckedParcel

BOW_TIE = [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]]
SQUARE = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]


def drawn(geo_type, coordinates, code="EPSG:3857"):
    return json_dumps(
        {
            "type": geo_type,
            "coordinates": coordinates,
            "crs": {"type": "name", "properties": {"name": code}},
        }
    )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeometryCheck(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[CheckedParcel._name]

    def test_a_valid_outline_has_no_problem(self):
        self.assertIsNone(
            self.Parcel.get_geometry_problem("area", drawn("Polygon", SQUARE))
        )

    def test_a_crossing_outline_is_named_where_it_crosses(self):
        problem = self.Parcel.get_geometry_problem("area", drawn("Polygon", BOW_TIE))
        self.assertEqual(problem["message"], "The outline crosses itself here.")
        self.assertEqual(problem["location"], (5.0, 5.0))

    def test_the_check_refuses_what_saving_refuses(self):
        value = drawn("Polygon", BOW_TIE)
        self.assertIsNotNone(self.Parcel.get_geometry_problem("area", value))
        with self.assertRaises(ValidationError):
            self.Parcel.create({"area": value})

    def test_a_repair_that_saving_would_do_silently_is_still_shown(self):
        value = drawn("MultiPolygon", [BOW_TIE])
        problem = self.Parcel.get_geometry_problem("zones", value)
        self.assertEqual(problem["message"], "The outline crosses itself here.")
        parcel = self.Parcel.create({"zones": value})
        self.assertEqual(len(parcel.zones.geoms), 2, "saved as two triangles")

    def test_the_place_is_given_in_the_map_s_coordinates(self):
        # the field stores 4326, the map draws 3857: the crossing is
        # reported in the map's metres, where the marker goes
        metres = [[[x * 1000, y * 1000] for x, y in BOW_TIE[0]]]
        problem = self.Parcel.get_geometry_problem(
            "area_wgs84", drawn("Polygon", metres)
        )
        x, y = problem["location"]
        self.assertAlmostEqual(x, 5000, delta=1)
        self.assertAlmostEqual(y, 5000, delta=50)

    def test_a_hole_outside_its_outline_is_named(self):
        problem = self.Parcel.get_geometry_problem(
            "area",
            drawn(
                "Polygon",
                [*SQUARE, [[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]],
            ),
        )
        self.assertEqual(problem["message"], "A hole reaches outside the outline here.")
        self.assertIsNotNone(problem["location"])

    def test_two_parts_for_a_single_polygon_field_are_explained(self):
        far_square = [[[x + 50, y] for x, y in SQUARE[0]]]
        problem = self.Parcel.get_geometry_problem(
            "area", drawn("MultiPolygon", [SQUARE, far_square])
        )
        self.assertIn("2 separate Polygon parts", problem["message"])
        self.assertIsNone(problem["location"])

    def test_a_value_that_is_no_geometry_is_explained(self):
        problem = self.Parcel.get_geometry_problem("area", "not a shape")
        self.assertIn("not a geometry", problem["message"])

    def test_too_many_points_are_refused_before_saving(self):
        self.env["ir.config_parameter"].set_param("geoengine.max_geometry_size", "10")
        problem = self.Parcel.get_geometry_problem("area", drawn("Polygon", SQUARE))
        self.assertIn("too many points", problem["message"])

    def test_only_geometry_fields_and_readers_of_the_model_are_checked(self):
        with self.assertRaises(ValueError):
            self.Parcel.get_geometry_problem("name", drawn("Polygon", SQUARE))
        reader = self.env["res.users"].create(
            {"name": "outline checker", "login": "geoengine_outline_checker"}
        )
        with self.assertRaises(AccessError):
            self.Parcel.with_user(reader).get_geometry_problem(
                "area", drawn("Polygon", SQUARE)
            )

    def test_the_map_view_names_the_geometry_it_draws(self):
        # the Draw tool picks the view's geometry field and its shape type
        # from these keys; without them it had no field to draw
        view = self.env["ir.ui.view"].create(
            {
                "name": "parcels",
                "model": self.Parcel._name,
                "type": "geoengine",
                "arch": '<geoengine editable="1"><field name="name"/>'
                '<field name="area"/><templates><t t-name="info_box">'
                '<div><t t-out="record.name"/></div></t></templates></geoengine>',
            }
        )
        described = self.Parcel.get_views([(view.id, "geoengine")])["models"][
            self.Parcel._name
        ]["fields"]["area"]
        self.assertEqual(
            (described["geo_type"], described["srid"], described["dim"]),
            ("Polygon", 3857, "2"),
        )

    def test_a_created_geometry_is_validated_once(self):
        # create converted each geometry for the INSERT and again for the
        # cache, parsing and validating it twice
        from unittest.mock import patch

        from odoo.addons.geoengine.models.fields import GeoField

        original = GeoField._check_geometry
        calls = []

        def counted(field, shape, record):
            calls.append(field.name)
            return original(field, shape, record)

        with patch.object(GeoField, "_check_geometry", counted):
            parcels = self.Parcel.create(
                [{"name": str(i), "area": drawn("Polygon", SQUARE)} for i in range(3)]
            )
            self.env.flush_all()
        self.assertEqual(calls, ["area"] * 3)
        self.assertEqual(parcels.mapped("area")[1].area, 100)
