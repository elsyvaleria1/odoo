from shapely.geometry import LineString, Point, Polygon

from odoo.tests import common


class GeoEngineTestCase(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.zurich_point = Point(948695.5, 6002729.5)
        cls.geneva_point = Point(673508.2, 5863471.4)

        cls.swiss_bbox = Polygon(
            [
                (600000, 5700000),
                (1200000, 5700000),
                (1200000, 6100000),
                (600000, 6100000),
                (600000, 5700000),
            ]
        )

        cls.test_highway = LineString(
            [
                (673508, 5863471),
                (750000, 5900000),
                (948695, 6002729),
            ]
        )

        cls.zurich_area = Polygon(
            [
                (940000, 5995000),
                (955000, 5995000),
                (955000, 6010000),
                (940000, 6010000),
                (940000, 5995000),
            ]
        )

        cls.paris_point = Point(260403.4, 6250373.2)
