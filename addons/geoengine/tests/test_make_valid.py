from shapely.geometry import Polygon

from odoo.exceptions import ValidationError

from ..models.fields import GeoPolygon
from .common import GeoEngineTestCase


class TestMakeValid(GeoEngineTestCase):
    def test_valid_geometry_passes_through(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857

        valid_poly = self.swiss_bbox
        self.assertTrue(valid_poly.is_valid)

        result = field._check_geometry(valid_poly, self.env["base"])
        self.assertTrue(result.is_valid)
        self.assertTrue(result.equals(valid_poly))

    def test_self_intersecting_polygon_repaired(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857

        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
        self.assertFalse(bowtie.is_valid)

        result = field._check_geometry(bowtie, self.env["base"])
        self.assertTrue(result.is_valid)
        self.assertFalse(result.is_empty)

    def test_repair_disabled_raises(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857

        self.env["ir.config_parameter"].sudo().set_param(
            "geoengine.auto_repair_geometry", "False"
        )

        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
        with self.assertRaises(ValidationError):
            field._check_geometry(bowtie, self.env["base"])

    def test_validation_disabled_skips_all(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857

        self.env["ir.config_parameter"].sudo().set_param(
            "geoengine.validate_geometry", "False"
        )

        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
        result = field._check_geometry(bowtie, self.env["base"])
        self.assertFalse(result.is_valid)

    def test_only_a_falsy_spelling_switches_validation_off(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("geoengine.auto_repair_geometry", "False")
        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])

        for spelling in ("True", "true", "1", "TRUE", "yes", "on", "garbage", ""):
            config.set_param("geoengine.validate_geometry", spelling)
            with (
                self.subTest(spelling=spelling),
                self.assertRaises(ValidationError),
            ):
                field._check_geometry(bowtie, self.env["base"])

        for spelling in ("False", "false", "0", "no", "off"):
            config.set_param("geoengine.validate_geometry", spelling)
            with self.subTest(spelling=spelling):
                self.assertFalse(
                    field._check_geometry(bowtie, self.env["base"]).is_valid
                )

    def test_only_a_falsy_spelling_switches_repair_off(self):
        field = GeoPolygon()
        field.name = "test_geom"
        field.srid = 3857
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("geoengine.validate_geometry", "True")
        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])

        for spelling in ("True", "true", "1", "TRUE", "yes", "on", "garbage", ""):
            config.set_param("geoengine.auto_repair_geometry", spelling)
            with self.subTest(spelling=spelling):
                self.assertTrue(
                    field._check_geometry(bowtie, self.env["base"]).is_valid
                )

        for spelling in ("False", "false", "0", "no", "off"):
            config.set_param("geoengine.auto_repair_geometry", spelling)
            with (
                self.subTest(spelling=spelling),
                self.assertRaises(ValidationError),
            ):
                field._check_geometry(bowtie, self.env["base"])
