import base64
import math
from itertools import starmap

from pyproj import Transformer
from shapely.geometry import Point, Polygon

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import SQL

from odoo.addons.geoengine.models.vector_tiles import (
    CELL_COUNT,
    CELL_KEY,
    CLUSTER_CELLS,
    FINE_GRID_MIN_ZOOM,
    LAYER_NAME,
    MAX_HEAT_CELLS,
    TILE_EXTENT,
    WEB_MERCATOR_WIDTH,
    HeatView,
    cell_size,
    render_tile,
)
from odoo.addons.geoengine.tests.mvt import decode
from odoo.addons.test_geoengine.models.vector_tiles import UTM_14N, TileSite


def tile_bounds(z, x, y):
    size = WEB_MERCATOR_WIDTH / 2**z
    minx = -WEB_MERCATOR_WIDTH / 2 + x * size
    maxy = WEB_MERCATOR_WIDTH / 2 - y * size
    return minx, maxy - size, minx + size, maxy


def tile_of(z, lon, lat):
    r = math.radians(lat)
    return (
        z,
        int((lon + 180) / 360 * 2**z),
        int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2**z),
    )


def tile_containing(z, px, py):
    size = WEB_MERCATOR_WIDTH / 2**z
    return (
        z,
        int((px + WEB_MERCATOR_WIDTH / 2) // size),
        int((WEB_MERCATOR_WIDTH / 2 - py) // size),
    )


def pixel(z, x, y, px, py):
    minx, _miny, _maxx, maxy = tile_bounds(z, x, y)
    size = WEB_MERCATOR_WIDTH / 2**z
    return (
        round((px - minx) / size * TILE_EXTENT),
        round((maxy - py) / size * TILE_EXTENT),
    )


class TileFixture:
    @classmethod
    def _setup_tiles(cls):
        cls.Site = cls.env[TileSite._name]
        fields_of = cls.env["ir.model.fields"]._get
        cls.field_ids = {
            name: fields_of(TileSite._name, name).id
            for name in (
                "position",
                "utm_position",
                "zone",
                "restricted_position",
                "score",
                "colour",
                "kind",
                "seen",
                "restricted_score",
            )
        }
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "tile fixture view",
                "model": TileSite._name,
                "type": "geoengine",
                "arch": """
                    <geoengine>
                        <field name="name"/>
                        <templates><t t-name="info_box"><div/></t></templates>
                    </geoengine>
                """,
            }
        )
        cls.fine_tile = tile_of(FINE_GRID_MIN_ZOOM, -107.65, 25.1)
        minx, miny, maxx, maxy = tile_bounds(*cls.fine_tile)
        step_x, step_y = (maxx - minx) / 6, (maxy - miny) / 6
        cls.grid_sites = cls.Site.create(
            [
                {
                    "name": f"G{i}{j}",
                    "score": float(i * 5 + j),
                    "colour": f"#0000{i}{j}",
                    "kind": "well" if (i + j) % 2 else "pump",
                    "seen": f"2026-09-{i + j + 1:02d}",
                    "position": f"POINT({minx + (i + 1) * step_x} {miny + (j + 1) * step_y})",
                }
                for i in range(5)
                for j in range(5)
            ]
        )
        cls.far_site = cls.Site.create(
            {"name": "far", "score": 99.0, "position": "POINT(0 0)"}
        )
        cls.plain = cls.env["res.users"].create(
            {
                "name": "tile map user",
                "login": "geoengine_tile_plain",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        cls.env["ir.access"].create(
            {
                "name": "tile site read, secrets excepted",
                "model_id": cls.env["ir.model"]._get_id(TileSite._name),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('name', '!=', 'G22')]",
            }
        )

    def _layer(self, geo="position", **values):
        return self.env["geoengine.vector.layer"].create(
            {
                "name": "tile layer",
                "view_id": self.view.id,
                "geo_field_id": self.field_ids[geo],
                "geo_repr": "basic",
            }
            | values
        )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestVectorTiles(TransactionCase, TileFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_tiles()

    def _features(self, layer, z, x, y, domain=None):
        result = layer.get_tile(z, x, y, domain)
        self.assertFalse(result["too_dense"])
        return decode(base64.b64decode(result["tile"])).get(LAYER_NAME, [])

    def test_a_fine_tile_draws_every_record_inside_it_with_its_id_and_pixel(self):
        features = self._features(self._layer(), *self.fine_tile)
        self.assertEqual(sorted(f.id for f in features), sorted(self.grid_sites.ids))
        for feature in features:
            site = self.Site.browse(feature.id)
            self.assertEqual(
                feature.geometry,
                [[pixel(*self.fine_tile, site.position.x, site.position.y)]],
                site.name,
            )

    def test_a_fine_tile_carries_the_styled_fields_in_their_own_types(self):
        layer = self._layer(
            geo_repr="colored",
            attribute_field_id=self.field_ids["score"],
            color_field_id=self.field_ids["colour"],
            classification="interval",
            nb_class=3,
        )
        features = {f.id: f for f in self._features(layer, *self.fine_tile)}
        for site in self.grid_sites:
            self.assertEqual(
                features[site.id].properties,
                {CELL_COUNT: 1, "score": site.score, "colour": site.colour},
            )

    def test_text_like_attributes_arrive_as_their_stored_text(self):
        layer = self._layer(geo_repr="basic", attribute_field_id=self.field_ids["seen"])
        features = {f.id: f for f in self._features(layer, *self.fine_tile)}
        site = self.grid_sites[7]
        self.assertEqual(
            features[site.id].properties, {CELL_COUNT: 1, "seen": str(site.seen)}
        )
        layer.attribute_field_id = self.field_ids["kind"]
        features = {f.id: f for f in self._features(layer, *self.fine_tile)}
        self.assertEqual(
            features[site.id].properties, {CELL_COUNT: 1, "kind": site.kind}
        )

    def test_the_map_domain_selects_the_population(self):
        features = self._features(
            self._layer(), *self.fine_tile, domain=[("score", ">=", 20)]
        )
        self.assertEqual(
            sorted(f.id for f in features),
            sorted(self.grid_sites.filtered(lambda s: s.score >= 20).ids),
        )

    def test_archived_records_stay_off_the_map(self):
        self.grid_sites[0].active = False
        features = self._features(self._layer(), *self.fine_tile)
        self.assertNotIn(self.grid_sites[0].id, {f.id for f in features})
        self.assertEqual(len(features), len(self.grid_sites) - 1)

    def test_record_rules_apply_to_the_tile(self):
        layer = self._layer().with_user(self.plain)
        features = self._features(layer, *self.fine_tile)
        hidden = self.grid_sites.filtered(lambda s: s.name == "G22")
        self.assertTrue(hidden)
        self.assertEqual(
            sorted(f.id for f in features), sorted((self.grid_sites - hidden).ids)
        )

    def test_a_geometry_the_user_may_not_read_is_refused(self):
        layer = self._layer(geo="restricted_position").with_user(self.plain)
        with self.assertRaises(AccessError):
            layer.get_tile(*self.fine_tile)

    def test_a_styled_field_the_user_may_not_read_is_refused(self):
        layer = self._layer(
            geo_repr="colored",
            attribute_field_id=self.field_ids["restricted_score"],
            classification="interval",
            nb_class=3,
        ).with_user(self.plain)
        with self.assertRaises(AccessError):
            layer.get_tile(*self.fine_tile)

    def test_points_below_the_fine_grid_are_counted_in_bubble_sized_cells(self):
        z = FINE_GRID_MIN_ZOOM - 4
        tile = tile_of(z, -107.65, 25.1)
        minx, miny, maxx, maxy = tile_bounds(*tile)
        loner = self.Site.create(
            {
                "name": "loner",
                "score": 42.0,
                "position": f"POINT({minx + (maxx - minx) * 0.9} {miny + (maxy - miny) * 0.1})",
            }
        )
        layer = self._layer(
            geo_repr="colored",
            attribute_field_id=self.field_ids["score"],
            classification="interval",
            nb_class=3,
        )
        features = self._features(layer, *tile)
        cell = (maxx - minx) / CLUSTER_CELLS
        sites = self.grid_sites | loner
        expected = {}
        for site in sites:
            key = (
                math.floor(site.position.x / cell),
                math.floor(site.position.y / cell),
            )
            expected.setdefault(key, []).append(site)
        self.assertEqual(
            sorted(f.properties[CELL_COUNT] for f in features),
            sorted(len(members) for members in expected.values()),
        )
        self.assertEqual(sum(f.properties[CELL_COUNT] for f in features), len(sites))
        [lone] = [f for f in features if f.id == loner.id]
        self.assertEqual(lone.properties, {CELL_COUNT: 1, "score": 42.0})
        for feature in features:
            if feature.properties[CELL_COUNT] > 1:
                self.assertIsNone(feature.id)
                self.assertEqual(set(feature.properties), {CELL_COUNT})

    def test_records_stacked_in_one_place_are_counted_at_any_zoom(self):
        minx, miny, maxx, maxy = tile_bounds(*self.fine_tile)
        px, py = minx + (maxx - minx) * 0.95, miny + (maxy - miny) * 0.95
        stacked = self.Site.create(
            [{"name": f"fix {i}", "position": f"POINT({px} {py})"} for i in range(50)]
        )
        for z in (FINE_GRID_MIN_ZOOM, FINE_GRID_MIN_ZOOM + 4):
            features = self._features(self._layer(), *tile_containing(z, px, py))
            [cell] = [f for f in features if f.properties[CELL_COUNT] > 1]
            size = cell_size(z)
            self.assertEqual(
                cell.properties,
                {
                    CELL_COUNT: len(stacked),
                    CELL_KEY: f"{z}/{math.floor(px / size)}/{math.floor(py / size)}",
                },
            )
            self.assertIsNone(cell.id)

    def _stacked_cell(self, names):
        minx, miny, maxx, maxy = tile_bounds(*self.fine_tile)
        px, py = minx + (maxx - minx) * 0.05, miny + (maxy - miny) * 0.05
        stacked = self.Site.create(
            [{"name": name, "position": f"POINT({px} {py})"} for name in names]
        )
        features = self._features(self._layer(), *self.fine_tile)
        [cell] = [f for f in features if f.properties[CELL_COUNT] > 1]
        return stacked, cell.properties[CELL_KEY]

    def test_a_stacked_cell_lists_exactly_its_records(self):
        stacked, key = self._stacked_cell([f"stack {i}" for i in range(12)])
        result = self._layer().get_cell_records(key)
        self.assertEqual(
            sorted(row["id"] for row in result["records"]), sorted(stacked.ids)
        )
        self.assertEqual(
            {row["display_name"] for row in result["records"]},
            set(stacked.mapped("display_name")),
        )
        self.assertFalse(result["more"])
        limited = self._layer().get_cell_records(key, None, 5)
        self.assertEqual(
            [row["id"] for row in limited["records"]],
            self.Site.search([("id", "in", stacked.ids)], limit=5).ids,
            "the first records in the model's order are listed",
        )
        self.assertTrue(limited["more"])

    def test_a_cell_lists_what_the_domain_and_record_rules_allow(self):
        stacked, key = self._stacked_cell(["G22", "stack a", "stack b"])
        plain = self._layer().with_user(self.plain).get_cell_records(key)
        self.assertEqual(
            sorted(row["id"] for row in plain["records"]),
            sorted(stacked.filtered(lambda s: s.name != "G22").ids),
        )
        narrowed = self._layer().get_cell_records(key, [("name", "=", "stack a")])
        self.assertEqual(
            [row["display_name"] for row in narrowed["records"]], ["stack a"]
        )

    def test_a_malformed_cell_is_refused(self):
        for key in ("", "1/2", "a/b/c", "99/0/0", f"3/{2**40}/0"):
            with self.subTest(key=key), self.assertRaises(UserError):
                self._layer().get_cell_records(key)

    def test_polygons_are_never_counted_in_cells(self):
        minx, miny, maxx, _maxy = tile_bounds(*self.fine_tile)
        width = maxx - minx
        site = self.Site.create(
            {
                "name": "field",
                "zone": Polygon(
                    [
                        (minx + width * 0.2, miny + width * 0.2),
                        (minx + width * 0.6, miny + width * 0.2),
                        (minx + width * 0.6, miny + width * 0.6),
                        (minx + width * 0.2, miny + width * 0.2),
                    ]
                ).wkt,
            }
        )
        features = self._features(
            self._layer(geo="zone"), *tile_of(FINE_GRID_MIN_ZOOM - 2, -107.65, 25.1)
        )
        self.assertEqual([f.id for f in features], [site.id])
        self.assertNotIn(CELL_COUNT, features[0].properties)

    def test_a_record_near_a_tile_edge_in_another_crs_is_kept(self):
        tile = (6, 12, 27)
        minx, miny, maxx, maxy = tile_bounds(*tile)
        inside = ((minx + maxx) / 2, miny + (maxy - miny) * 0.001)
        to_utm = Transformer.from_crs(3857, UTM_14N, always_xy=True)
        corners = Polygon(
            list(
                starmap(
                    to_utm.transform,
                    ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)),
                )
            )
        )
        utm = Point(to_utm.transform(*inside))
        self.assertFalse(
            corners.contains(utm),
            "the fixture point must lie where a corner-transformed tile drops it",
        )
        site = self.Site.create({"name": "edge", "utm_position": utm.wkt})
        features = self._features(self._layer(geo="utm_position"), *tile)
        self.assertEqual([f.properties[CELL_COUNT] for f in features], [1])
        self.assertEqual(features[0].id, site.id)

    def test_tiles_outside_the_grid_or_not_integers_are_refused(self):
        layer = self._layer()
        for z, x, y in ((-1, 0, 0), (25, 0, 0), (2, 4, 0), (2, 0, -1), (2, "1", 0)):
            with self.subTest(z=z, x=x, y=y), self.assertRaises(UserError):
                layer.get_tile(z, x, y)

    def test_an_empty_tile_is_an_empty_tile(self):
        self.assertEqual(self._features(self._layer(), 14, 0, 0), [])

    def test_a_tile_over_its_budget_is_reported_and_the_session_survives(self):
        self.env["ir.config_parameter"].set_param("geoengine.tile_timeout_ms", "50")
        self.env.cr.execute("SHOW statement_timeout")
        [before] = self.env.cr.fetchone()
        self.assertIsNone(render_tile(self.env, SQL("SELECT pg_sleep(1)::text::bytea")))
        self.env.cr.execute("SHOW statement_timeout")
        self.assertEqual(self.env.cr.fetchone(), (before,))
        self.assertEqual(self.Site.search_count([("name", "=", "far")]), 1)

    def test_a_rendered_tile_leaves_the_statement_timeout_as_it_found_it(self):
        self.env.cr.execute("SHOW statement_timeout")
        [before] = self.env.cr.fetchone()
        self._features(self._layer(), *self.fine_tile)
        self.env.cr.execute("SHOW statement_timeout")
        self.assertEqual(self.env.cr.fetchone(), (before,))

    def test_a_pending_write_survives_a_tile_over_its_budget(self):
        self.env["ir.config_parameter"].set_param("geoengine.tile_timeout_ms", "50")
        site = self.grid_sites[3]
        site.name = "renamed before the tile"
        query = self.Site._search([("name", "=", "renamed before the tile")])
        self.assertIsNone(
            render_tile(
                self.env,
                SQL("SELECT pg_sleep(1)::text::bytea FROM (%s) AS q", query.select()),
            )
        )
        self.env.cr.execute(
            SQL(
                "SELECT name FROM %s WHERE id = %s",
                SQL.identifier(self.Site._table),
                site.id,
            )
        )
        self.assertEqual(self.env.cr.fetchone(), ("renamed before the tile",))

    def test_the_extent_frames_the_population_in_web_mercator(self):
        layer = self._layer()
        xs = [site.position.x for site in self.grid_sites]
        ys = [site.position.y for site in self.grid_sites]
        extent = layer.get_tile_extent([("name", "like", "G")])
        for got, want in zip(extent, (min(xs), min(ys), max(xs), max(ys)), strict=True):
            self.assertAlmostEqual(got, want, delta=0.01)

    def test_the_extent_of_another_crs_is_returned_in_web_mercator(self):
        site = self.Site.create(
            {"name": "utm", "utm_position": "POINT(500000 2800000)"}
        )
        to_mercator = Transformer.from_crs(UTM_14N, 3857, always_xy=True)
        x, y = to_mercator.transform(500000, 2800000)
        extent = self._layer(geo="utm_position").get_tile_extent([("id", "=", site.id)])
        for got, want in zip(extent, (x, y, x, y), strict=True):
            self.assertAlmostEqual(got, want, delta=0.01)

    def test_the_extent_follows_record_rules_and_is_none_when_empty(self):
        layer = self._layer().with_user(self.plain)
        self.assertIsNone(layer.get_tile_extent([("name", "=", "G22")]))
        self.assertIsNone(layer.get_tile_extent([("name", "=", "nobody")]))
        self.assertIsNotNone(layer.get_tile_extent([("name", "=", "G21")]))

    def _heat_layer(self, **values):
        return self._layer(geo_repr="heatmap", **values)

    def test_heat_cells_sum_the_records_in_view(self):
        extent = list(tile_bounds(*self.fine_tile))
        result = self._heat_layer().get_heat_cells(extent, FINE_GRID_MIN_ZOOM)
        self.assertFalse(result["too_dense"])
        self.assertEqual(sum(w for _x, _y, w in result["cells"]), len(self.grid_sites))
        minx, miny, maxx, maxy = extent
        for x, y, _w in result["cells"]:
            self.assertTrue(minx <= x <= maxx and miny <= y <= maxy)

    def test_heat_cells_are_weighted_by_the_layer_s_weight_field(self):
        layer = self._heat_layer(heatmap_weight_field_id=self.field_ids["score"])
        result = layer.get_heat_cells(
            list(tile_bounds(*self.fine_tile)), FINE_GRID_MIN_ZOOM
        )
        self.assertAlmostEqual(
            sum(w for _x, _y, w in result["cells"]),
            sum(self.grid_sites.mapped("score")),
        )

    def test_heat_cells_follow_the_domain_and_record_rules(self):
        extent = list(tile_bounds(*self.fine_tile))
        plain = (
            self._heat_layer()
            .with_user(self.plain)
            .get_heat_cells(extent, FINE_GRID_MIN_ZOOM)
        )
        self.assertEqual(
            sum(w for _x, _y, w in plain["cells"]), len(self.grid_sites) - 1
        )
        narrowed = self._heat_layer().get_heat_cells(
            extent, FINE_GRID_MIN_ZOOM, [("score", "<", 5)]
        )
        self.assertEqual(sum(w for _x, _y, w in narrowed["cells"]), 5)

    def test_a_world_view_is_summed_into_a_bounded_number_of_cells(self):
        half = WEB_MERCATOR_WIDTH / 2
        result = self._heat_layer().get_heat_cells([-half, -half, half, half], 0)
        self.assertEqual(
            sum(w for _x, _y, w in result["cells"]), len(self.Site.search([]))
        )
        view = HeatView.checked(self.env, [-half, -half, half, half], 12)
        self.assertLessEqual((2 * half / view.cell) ** 2, MAX_HEAT_CELLS * 1.0001)

    def test_a_malformed_heat_view_is_refused(self):
        layer = self._heat_layer()
        for extent, zoom in (
            ([0, 0, 0, 0], 3),
            ([1, 2, 3], 3),
            (["a", 0, 1, 1], 3),
            ([0, 0, 1, 1], 40),
        ):
            with self.subTest(extent=extent, zoom=zoom), self.assertRaises(UserError):
                layer.get_heat_cells(extent, zoom)
