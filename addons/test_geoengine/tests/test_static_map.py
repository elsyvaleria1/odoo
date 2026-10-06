import io
import math
import pathlib
import tempfile
from unittest.mock import Mock, patch

import weasyprint
from lxml import etree
from PIL import Image
from shapely.geometry import LineString, Point, Polygon

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.models import static_map
from odoo.addons.geoengine.models.static_map import (
    MapItem,
    MapStyle,
    TileFetcher,
    frame_for,
    render_static_map,
)
from odoo.addons.test_geoengine.models.static_map import MapSite

SVG = "{http://www.w3.org/2000/svg}"


def _png(colour=(200, 220, 240)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), colour).save(buffer, "PNG")
    return buffer.getvalue()


class FakeFetcher:
    attribution = "© test tiles"

    def __init__(self, data=None):
        self.data = _png() if data is None else data
        self.asked = []

    def tile(self, z, x, y):
        self.asked.append((z, x, y))
        return self.data or None


@tagged("post_install", "-at_install", "geoengine_audit")
class TestStaticMap(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site = cls.env[MapSite._name]

    def _svg(self, items, **options):
        markup = render_static_map(self.env, items, **options)
        return etree.fromstring(str(markup).encode())

    def test_a_lone_point_is_centred_and_framed_a_few_streets_wide(self):
        tree = self._svg(
            [MapItem(Point(-107.65, 25.1), 4326)], width=600, height=400, basemap=False
        )
        [circle] = tree.iter(f"{SVG}circle")
        self.assertAlmostEqual(float(circle.get("cx")), 300, delta=0.1)
        self.assertAlmostEqual(float(circle.get("cy")), 200, delta=0.1)
        frame = frame_for([Point(0, 0)], 600, 400, 24)
        span = static_map.POINT_SPAN_M
        tightest = max(span / (600 - 48), span / (400 - 48))
        # A whole zoom level is at most twice the tightest resolution.
        self.assertGreaterEqual(frame.resolution, tightest)
        self.assertLess(frame.resolution, 2 * tightest)

    def test_the_frame_holds_every_item_inside_its_padding(self):
        line = LineString([(0, 0), (50_000, 20_000)])
        frame = frame_for([line], 640, 360, 24)
        for x, y in line.coords:
            px, py = frame.pixel(x, y)
            self.assertTrue(24 - 0.5 <= px <= 640 - 24 + 0.5, px)
            self.assertTrue(0 <= py <= 360, py)
        tighter = static_map.Frame(frame.minx, frame.maxy, frame.zoom + 1, 640, 360)
        self.assertGreater(50_000 / tighter.resolution, 640 - 48)

    def test_every_shape_is_drawn_and_labels_are_escaped(self):
        tree = self._svg(
            [
                MapItem(LineString([(0, 0), (1000, 1000), (2000, 0)]), 3857),
                MapItem(
                    Polygon(
                        [(0, 0), (3000, 0), (3000, 3000), (0, 0)],
                        [[(500, 200), (1000, 200), (1000, 600), (500, 200)]],
                    ),
                    3857,
                ),
                MapItem(Point(1500, 1500), 3857, MapStyle(label="<b>1</b>")),
            ],
            basemap=False,
        )
        self.assertEqual(len(list(tree.iter(f"{SVG}polyline"))), 1)
        [path] = tree.iter(f"{SVG}path")
        self.assertEqual(path.get("d").count("M"), 2, "the hole is its own ring")
        [label] = tree.iter(f"{SVG}text")
        self.assertEqual(label.text, "<b>1</b>")
        circles = list(tree.iter(f"{SVG}circle"))
        self.assertGreater(
            list(tree).index(circles[0]),
            list(tree).index(path),
            "points are drawn above lines and areas",
        )

    def test_a_long_track_is_simplified_to_the_pixel(self):
        track = LineString([(i, math.sin(i / 50) * 10) for i in range(0, 100_000, 5)])
        [polyline] = self._svg([MapItem(track, 3857)], basemap=False).iter(
            f"{SVG}polyline"
        )
        self.assertLess(len(polyline.get("points").split()), 2000)
        self.assertGreater(len(track.coords), 19_000)

    def test_the_basemap_covers_the_frame_and_credits_its_source(self):
        fetcher = FakeFetcher()
        tree = self._svg(
            [MapItem(Point(-107.65, 25.1), 4326)],
            width=640,
            height=360,
            fetcher=fetcher,
        )
        images = list(tree.iter(f"{SVG}image"))
        self.assertEqual(len(images), len(fetcher.asked))
        lefts = [float(i.get("x")) for i in images]
        tops = [float(i.get("y")) for i in images]
        self.assertLessEqual(min(lefts), 0)
        self.assertLessEqual(min(tops), 0)
        self.assertGreaterEqual(max(lefts) + 256, 640)
        self.assertGreaterEqual(max(tops) + 256, 360)
        self.assertEqual(list(tree.iter(f"{SVG}text"))[-1].text, "© test tiles")

    def test_a_map_without_tiles_is_still_drawn_without_credit(self):
        tree = self._svg(
            [MapItem(Point(-107.65, 25.1), 4326)], fetcher=FakeFetcher(data=b"")
        )
        self.assertEqual(list(tree.iter(f"{SVG}image")), [])
        self.assertEqual(list(tree.iter(f"{SVG}text")), [])
        self.assertEqual(len(list(tree.iter(f"{SVG}circle"))), 1)

    def test_nothing_to_draw_is_no_map(self):
        self.assertIsNone(render_static_map(self.env, [MapItem(Point(), 3857)]))
        self.assertIsNone(render_static_map(self.env, []))

    def test_a_tile_is_downloaded_once_and_then_read_from_disk(self):
        fetcher = TileFetcher(self.env)
        with tempfile.TemporaryDirectory() as cache:
            fetcher.cache_dir = pathlib.Path(cache)
            with patch.object(
                TileFetcher, "_download", return_value=_png()
            ) as download:
                first = fetcher.tile(10, 198, 447)
                second = fetcher.tile(10, 198, 447)
            self.assertEqual(first, second)
            self.assertEqual(download.call_count, 1)
            self.assertEqual(len(list(pathlib.Path(cache).iterdir())), 1)

    def test_a_tile_is_fetched_through_ir_egress(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, content=_png())
        with patch.object(
            type(self.env["ir.egress"]), "session", return_value=session
        ) as egress:
            data = TileFetcher(self.env)._download("https://tiles.example.com/1.png")
        egress.assert_called_once_with(purpose="geoengine_static_map")
        self.assertEqual(data, _png())

    def test_the_tile_server_is_configurable(self):
        self.env["ir.config_parameter"].set_param(
            "geoengine.static_map_tile_url", "https://tiles.example.com/{z}/{x}/{y}.png"
        )
        fetcher = TileFetcher(self.env)
        with (
            tempfile.TemporaryDirectory() as cache,
            patch.object(TileFetcher, "_download", return_value=None) as download,
        ):
            fetcher.cache_dir = pathlib.Path(cache)
            self.assertIsNone(fetcher.tile(3, 1, 2))
        download.assert_called_once_with("https://tiles.example.com/3/1/2.png")

    def test_weasyprint_prints_the_map_with_its_basemap(self):
        markup = render_static_map(
            self.env, [MapItem(Point(-107.65, 25.1), 4326)], fetcher=FakeFetcher()
        )
        pdf = weasyprint.HTML(string=f"<html><body>{markup}</body></html>").write_pdf()
        self.assertIn(b"/Subtype /Image", pdf)

    def test_records_draw_their_readable_geometries(self):
        site = self.Site.create(
            {
                "name": "well",
                "position": "POINT(-107.65 25.1)",
                "area": "POLYGON((-11983000 2886000, -11982000 2886000, -11982000 2887000, -11983000 2886000))",
                "restricted": "POINT(-100 20)",
            }
        )
        with patch.object(static_map, "TileFetcher", return_value=FakeFetcher(b"")):
            plain = self.env["res.users"].create(
                {"name": "map printer", "login": "geoengine_static_printer"}
            )
            tree = etree.fromstring(
                str(site.with_user(plain)._geo_static_map()).encode()
            )
            self.assertEqual(len(list(tree.iter(f"{SVG}circle"))), 1)
            self.assertEqual(len(list(tree.iter(f"{SVG}path"))), 1)
            only_area = etree.fromstring(str(site._geo_static_map("area")).encode())
            self.assertEqual(list(only_area.iter(f"{SVG}circle")), [])
        self.assertIsNone(self.Site.create({"name": "nowhere"})._geo_static_map())
