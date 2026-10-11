import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .test_ogc_features import OgcFixture
from .test_vector_tiles import TileFixture, tile_bounds
from odoo.addons.geoengine.models import ogc_features as ogc
from odoo.addons.geoengine.tests.mvt import decode

BUDGETS = {
    "point_tile": 7,
    "polygon_tile": 7,
    "tile_extent": 7,
    "heat_cells": 7,
    "cell_records": 4,
    "ogc_collection": 5,
    "ogc_items_page": 8,
}


@tagged("post_install", "-at_install", "geoengine_audit")
class TestQueryBudgets(TransactionCase, TileFixture, OgcFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_tiles()
        tile_site, tile_plain = cls.Site, cls.plain
        cls._setup_ogc()
        cls.ogc_plain = cls.plain
        cls.Site, cls.plain = tile_site, tile_plain

    def _measure(self, name, call):
        call()
        self.env.invalidate_all()
        with self.assertQueryCount(BUDGETS[name]):
            call()

    def test_the_map_server_paths_keep_their_statement_counts(self):
        user_env = self.env(user=self.plain)
        points = self._layer().with_env(user_env)
        zones = self._layer(geo="zone").with_env(user_env)
        heat = self._layer(geo_repr="heatmap").with_env(user_env)
        z, x, y = self.fine_tile
        extent = list(tile_bounds(*self.fine_tile))
        minx, miny, maxx, maxy = extent
        stacked = f"POINT({minx + (maxx - minx) * 0.05} {miny + (maxy - miny) * 0.05})"
        self.Site.create(
            [{"name": f"stack {i}", "position": stacked} for i in range(5)]
        )
        tile = decode(base64.b64decode(points.get_tile(z, x, y)["tile"]))
        cell = next(
            feature.properties["cell"]
            for feature in tile["features"]
            if feature.properties.get("cell")
        )
        reader_env = self.env(user=self.ogc_plain)
        collection = ogc.find_collection(reader_env, "geoengine.test.ogc.site.position")
        measures = {
            "point_tile": lambda: points.get_tile(z, x, y),
            "polygon_tile": lambda: zones.get_tile(z - 2, x // 4, y // 4),
            "tile_extent": lambda: points.get_tile_extent([]),
            "heat_cells": lambda: heat.get_heat_cells(extent, z),
            "cell_records": lambda: points.get_cell_records(cell),
            "ogc_collection": lambda: ogc.collection_description(
                reader_env, collection, "http://x"
            ),
            "ogc_items_page": lambda: ogc.items(reader_env, collection, "http://x"),
        }
        for name, call in measures.items():
            with self.subTest(path=name):
                self._measure(name, call)
