from odoo.models import READ_GROUP_AGGREGATE
from odoo.tests import common
from odoo.tools import SQL

from ..models.fields import (
    GEO_AGGREGATES,
    GeoField,
    GeoLine,
    GeoMultiPolygon,
    GeoPoint,
    GeoPolygon,
)


class TestSpatialAggregateRegistration(common.TransactionCase):
    def test_geo_aggregates_registered(self):
        for name in ("geo_union", "geo_collect", "geo_extent", "geo_centroid"):
            self.assertIn(name, READ_GROUP_AGGREGATE)

    def test_geo_aggregate_sql_generation(self):
        test_cases = {
            "geo_union": "ST_Union",
            "geo_collect": "ST_Collect",
            "geo_extent": "ST_Extent",
            "geo_centroid": "ST_Centroid",
        }

        for agg_name, expected_func in test_cases.items():
            agg_fn = GEO_AGGREGATES[agg_name]
            result = agg_fn(SQL("test_col"))
            sql_str = str(result)
            self.assertIn(
                expected_func,
                sql_str,
                f"Aggregate {agg_name} should generate SQL with {expected_func}",
            )

    def test_geo_field_has_default_aggregator(self):
        for cls in (GeoField, GeoPoint, GeoLine, GeoPolygon, GeoMultiPolygon):
            self.assertEqual(
                cls.aggregator,
                "geo_collect",
                f"{cls.__name__} should have 'geo_collect' as default aggregator",
            )

    def test_spatial_aggregate_on_non_geo_field_raises(self):
        with self.assertRaises(ValueError):
            self.env["res.partner"]._read_group(
                domain=[("id", "=", -1)],
                groupby=[],
                aggregates=["name:geo_union"],
            )
