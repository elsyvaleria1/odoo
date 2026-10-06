import logging

import pyproj
from shapely.geometry import Point
from shapely.ops import transform

from odoo.tests.common import TransactionCase

logger = logging.getLogger(__name__)


class TestCoordinateTransformation(TransactionCase):
    def test_wgs84_to_web_mercator_mexico_city(self):
        lat, lon = 19.4326, -99.1332

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        point_wgs84 = Point(lon, lat)
        point_mercator = transform(transformer.transform, point_wgs84)

        self.assertAlmostEqual(point_mercator.x, -11035457, delta=5000)
        self.assertAlmostEqual(point_mercator.y, 2207072, delta=5000)

    def test_wgs84_to_web_mercator_equator(self):
        lat, lon = 0.0, 0.0

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        point_wgs84 = Point(lon, lat)
        point_mercator = transform(transformer.transform, point_wgs84)

        self.assertAlmostEqual(point_mercator.x, 0.0, delta=1.0)
        self.assertAlmostEqual(point_mercator.y, 0.0, delta=1.0)

    def test_wgs84_to_web_mercator_prime_meridian(self):
        lat, lon = 0.0, 0.0

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        point_wgs84 = Point(lon, lat)
        point_mercator = transform(transformer.transform, point_wgs84)

        self.assertAlmostEqual(point_mercator.x, 0.0, delta=1.0)

    def test_web_mercator_bounds(self):
        lat, lon = 85.0, 0.0
        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        point_wgs84 = Point(lon, lat)
        point_mercator = transform(transformer.transform, point_wgs84)

        self.assertGreater(abs(point_mercator.y), 10000000)

    def test_transformation_precision(self):
        lat, lon = 19.432608, -99.133209

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        point_wgs84 = Point(lon, lat)
        point_mercator = transform(transformer.transform, point_wgs84)

        inverse_transformer = pyproj.Transformer.from_crs(
            "EPSG:3857",
            "EPSG:4326",
            always_xy=True,
        )
        point_back = transform(inverse_transformer.transform, point_mercator)

        self.assertAlmostEqual(point_back.x, lon, places=6)
        self.assertAlmostEqual(point_back.y, lat, places=6)

    def test_multiple_mexico_locations(self):
        locations = [
            ("Mexico City", 19.4326, -99.1332),
            ("Guadalajara", 20.6597, -103.3496),
            ("Monterrey", 25.6866, -100.3161),
            ("Cancun", 21.1619, -86.8515),
        ]

        transformer = pyproj.Transformer.from_crs(
            "EPSG:4326",
            "EPSG:3857",
            always_xy=True,
        )

        for name, lat, lon in locations:
            point_wgs84 = Point(lon, lat)
            point_mercator = transform(transformer.transform, point_wgs84)

            self.assertLess(
                point_mercator.x,
                0,
                f"{name} should be west of prime meridian",
            )

            self.assertGreater(
                point_mercator.y,
                0,
                f"{name} should be north of equator",
            )
