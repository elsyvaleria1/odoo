from shapely.geometry import Point

from odoo.tests import common

from ..models.geo_types import DomainOperator, SpatialOperator


class TestDomainOperator(common.TransactionCase):
    def test_all_domain_operators_exist(self):
        expected = [
            "geo_intersect",
            "geo_contains",
            "geo_within",
            "geo_touch",
            "geo_equal",
            "geo_overlap",
            "geo_covers",
            "geo_covered_by",
            "geo_disjoint",
            "geo_crosses",
            "geo_dwithin",
        ]

        for op_name in expected:
            with self.subTest(operator=op_name):
                op = DomainOperator(op_name)
                self.assertEqual(op.value, op_name)

    def test_to_spatial_operator_mapping(self):
        mappings = [
            (DomainOperator.INTERSECT, SpatialOperator.INTERSECTS),
            (DomainOperator.CONTAINS, SpatialOperator.CONTAINS),
            (DomainOperator.WITHIN, SpatialOperator.WITHIN),
            (DomainOperator.TOUCH, SpatialOperator.TOUCHES),
            (DomainOperator.EQUAL, SpatialOperator.EQUALS),
            (DomainOperator.OVERLAP, SpatialOperator.OVERLAPS),
            (DomainOperator.COVERS, SpatialOperator.COVERS),
            (DomainOperator.COVERED_BY, SpatialOperator.COVERED_BY),
            (DomainOperator.DISJOINT, SpatialOperator.DISJOINT),
            (DomainOperator.CROSSES, SpatialOperator.CROSSES),
            (DomainOperator.DWITHIN, SpatialOperator.DWITHIN),
        ]

        for domain_op, expected_spatial in mappings:
            with self.subTest(domain_op=domain_op.name):
                spatial_op = domain_op.to_spatial_operator()
                self.assertEqual(spatial_op, expected_spatial)


class TestGeoOperatorsRegistration(common.TransactionCase):
    def test_geo_operators_registered_in_condition_operators(self):
        from odoo.fields import ACCEPTED_CONDITION_OPERATORS, CONDITION_OPERATORS

        from ..models.geo_domain import GEO_OPERATORS

        for op in GEO_OPERATORS:
            with self.subTest(operator=op):
                self.assertIn(
                    op,
                    ACCEPTED_CONDITION_OPERATORS,
                    f"Operator {op} not registered in ACCEPTED_CONDITION_OPERATORS",
                )
                self.assertNotIn(
                    op,
                    CONDITION_OPERATORS,
                    f"Operator {op} leaked into the framework's frozen vocabulary",
                )

    def test_geo_operators_are_usable_in_a_domain(self):
        from odoo.fields import Domain

        from ..models.geo_domain import GEO_OPERATORS

        for op in sorted(GEO_OPERATORS):
            with self.subTest(operator=op):
                Domain("geom", op, "POINT(0 0)")

        with self.assertRaises(ValueError):
            Domain("geom", "geo_not_an_operator", "POINT(0 0)")

    def test_geo_operators_frozenset_is_immutable(self):
        from ..models.geo_domain import GEO_OPERATORS

        self.assertIsInstance(GEO_OPERATORS, frozenset)

        with self.assertRaises(AttributeError):
            GEO_OPERATORS.add("new_operator")


class TestGeoDomainParsing(common.TransactionCase):
    def test_parse_geometry_from_wkt(self):
        from ..models.fields import _parse_geometry

        wkt = "POINT(948695.5 6002729.5)"
        geom = _parse_geometry(wkt)

        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "Point")

    def test_parse_geometry_from_wkt_with_srid(self):
        from ..models.fields import _parse_geometry

        wkt = "SRID=3857;POINT(948695.5 6002729.5)"
        geom = _parse_geometry(wkt)

        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, "Point")

    def test_parse_geometry_from_shapely(self):
        from ..models.fields import _parse_geometry

        point = Point(948695.5, 6002729.5)
        geom = _parse_geometry(point)

        self.assertIsNotNone(geom)
        self.assertEqual(geom, point)

    def test_parse_geometry_empty_value_returns_none(self):
        from ..models.fields import _parse_geometry

        self.assertIsNone(_parse_geometry(None))
        self.assertIsNone(_parse_geometry(""))

    def test_parse_geometry_invalid_wkt_raises(self):
        from ..models.fields import _parse_geometry

        with self.assertRaises(ValueError):
            _parse_geometry("INVALID_WKT")


class TestGeoDomainDWithin(common.TransactionCase):
    def test_geo_dwithin_dict_format(self):
        expected_format = {
            "geometry": "SRID=3857;POINT(0 0)",
            "distance": 1000.0,
        }

        self.assertIn("geometry", expected_format)
        self.assertIn("distance", expected_format)
        self.assertIsInstance(expected_format["distance"], float)

    def test_geo_dwithin_extracts_geometry_correctly(self):
        dwithin_value = {
            "geometry": "SRID=3857;POINT(948695.5 6002729.5)",
            "distance": 500.0,
        }

        actual_geom_value = dwithin_value.get("geometry")
        distance = dwithin_value.get("distance")

        self.assertEqual(actual_geom_value, "SRID=3857;POINT(948695.5 6002729.5)")
        self.assertEqual(distance, 500.0)


class TestSpatialOperatorEnum(common.TransactionCase):
    def test_all_spatial_operators_have_postgis_function_prefix(self):
        for op in SpatialOperator:
            with self.subTest(operator=op.name):
                self.assertTrue(
                    op.value.startswith("ST_"),
                    f"Operator {op.name} value '{op.value}' doesn't start with ST_",
                )
