import pathlib
import re

from odoo.tests import TransactionCase, tagged

PAYLOAD_READERS = {
    "backgrounds": "static/src/geoengine/geoengine_model.js",
    "actives": "static/src/geoengine/geoengine_model.js",
    "projection": "static/src/geoengine/geoengine_model.js",
    "projections": "static/src/geoengine/geoengine_model.js",
    "default_map_extent": "static/src/geoengine/geoengine_model.js",
    "restricted_extent": "static/src/geoengine/geoengine_model.js",
    "default_map_zoom": "static/src/geoengine/geoengine_model.js",
    "render_engine": "static/src/geoengine/geoengine_model.js",
    "webgl_threshold": "static/src/geoengine/geoengine_model.js",
    "controls": "static/src/geoengine/geoengine_model.js",
    "validation": "static/src/geoengine/geoengine_model.js",
}

_LAYER_READER = "static/src/geoengine"


def _reader_pattern(key: str) -> str:
    # `.key`, `["key"]`, `{key}`/`{key,` destructuring or `key:` in a literal:
    # a plain word boundary matched `name`, `id`, `model` and `url` in any
    # file, which made "has a reader" vacuous for exactly those keys.
    escaped = re.escape(key)
    return rf"(\.{escaped}\b|[\"']{escaped}[\"']|[{{,]\s*{escaped}\s*[,}}:])"


VECTOR_LAYER_READERS = {
    "active_on_startup": "static/src/geoengine/geoengine_model.js",
    "attribute_field_name": _LAYER_READER,
    "begin_color": _LAYER_READER,
    "classification": _LAYER_READER,
    "cluster_distance": _LAYER_READER,
    "cluster_min_distance": _LAYER_READER,
    "color_field_name": _LAYER_READER,
    "display_polygon_labels": _LAYER_READER,
    "domain": _LAYER_READER,
    "end_color": _LAYER_READER,
    "geo_field_name": _LAYER_READER,
    "geo_repr": _LAYER_READER,
    "heatmap_blur": _LAYER_READER,
    "heatmap_radius": _LAYER_READER,
    "heatmap_weight_field_name": _LAYER_READER,
    "id": None,
    "layer_opacity": _LAYER_READER,
    "max_size": _LAYER_READER,
    "min_size": _LAYER_READER,
    "model": _LAYER_READER,
    "model_domain": _LAYER_READER,
    "name": _LAYER_READER,
    "nb_class": _LAYER_READER,
    "readonly": _LAYER_READER,
    "render_engine": _LAYER_READER,
    "resId": _LAYER_READER,
    "resModel": _LAYER_READER,
    "sequence": _LAYER_READER,
    "webgl_threshold": _LAYER_READER,
}

RASTER_LAYER_READERS = {
    "attribution": _LAYER_READER,
    "format_suffix": _LAYER_READER,
    "id": _LAYER_READER,
    "matrix_set": _LAYER_READER,
    "max_extent": _LAYER_READER,
    "max_zoom": _LAYER_READER,
    "name": _LAYER_READER,
    "opacity": _LAYER_READER,
    "overlay": "static/src/geoengine/geoengine_model.js",
    "params": _LAYER_READER,
    "params_wms": _LAYER_READER,
    "projection": _LAYER_READER,
    "raster_type": _LAYER_READER,
    "request_encoding": _LAYER_READER,
    "resolutions": _LAYER_READER,
    "server_type": _LAYER_READER,
    "url": _LAYER_READER,
    "wmts_layer": _LAYER_READER,
}

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGetLayersContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.view = next(
            (
                view
                for view in cls.env["ir.ui.view"].search([("type", "=", "geoengine")])
                if view.model in cls.env
            ),
            cls.env["ir.ui.view"],
        )

    def test_every_payload_key_is_declared(self):
        if not self.view:
            self.skipTest("no geoengine view installed")
        payload = self.env[self.view.model].get_layers(self.view.id)

        undeclared = set(payload) - set(PAYLOAD_READERS)
        self.assertFalse(
            undeclared,
            f"get_layers() sends {sorted(undeclared)} with no declared reader. "
            f"Add the reader, or stop sending the key.",
        )
        missing = set(PAYLOAD_READERS) - set(payload)
        self.assertFalse(
            missing,
            f"{sorted(missing)} is declared as read but no longer sent.",
        )

    def test_every_payload_key_has_a_live_reader(self):
        for key, reader in PAYLOAD_READERS.items():
            if reader is None:
                continue
            with self.subTest(key=key):
                path = MODULE_ROOT / reader
                self.assertTrue(path.exists(), f"{reader} does not exist")
                source = path.read_text(encoding="utf-8")
                self.assertRegex(
                    source,
                    _reader_pattern(key),
                    f"get_layers() sends {key!r} and {reader} never reads it",
                )

    def test_every_layer_key_is_declared(self):
        if not self.view:
            self.skipTest("no geoengine view installed")
        payload = self.env[self.view.model].get_layers(self.view.id)
        for kind, declared in (
            ("actives", VECTOR_LAYER_READERS),
            ("backgrounds", RASTER_LAYER_READERS),
        ):
            if not payload[kind]:
                continue
            with self.subTest(kind=kind):
                sent = set(payload[kind][0])
                undeclared = sent - set(declared)
                self.assertFalse(
                    undeclared,
                    f"get_layers() sends {sorted(undeclared)} on a {kind} layer "
                    f"with no declared reader. Add the reader, or stop sending it "
                    f"(see _VECTOR_LAYER_FIELDS / _RASTER_LAYER_FIELDS).",
                )
                missing = set(declared) - sent
                self.assertFalse(
                    missing,
                    f"{sorted(missing)} is declared as read but no longer sent.",
                )

    def test_every_layer_key_has_a_live_reader(self):
        for declared in (VECTOR_LAYER_READERS, RASTER_LAYER_READERS):
            for key, reader in declared.items():
                if reader is None:
                    continue
                with self.subTest(key=key):
                    path = MODULE_ROOT / reader
                    self.assertTrue(path.exists(), f"{reader} does not exist")
                    sources = (
                        [p.read_text(encoding="utf-8") for p in path.rglob("*.js")]
                        if path.is_dir()
                        else [path.read_text(encoding="utf-8")]
                    )
                    pattern = re.compile(_reader_pattern(key))
                    self.assertTrue(
                        any(pattern.search(source) for source in sources),
                        f"get_layers() sends {key!r} and {reader} never mentions it",
                    )

    def test_the_map_settings_survive_the_trip(self):
        if not self.view:
            self.skipTest("no geoengine view installed")
        settings = {
            "projection": "EPSG:3857",
            "default_map_extent": "-13173896.5, 1632778.9, -9633272.7, 3910375.8",
            "restricted_extent": "-20037508.3, -20037508.3, 20037508.3, 20037508.3",
            "default_map_zoom": 7,
        }
        if self.view.map_settings_id:
            self.view.map_settings_id.write(settings)
        else:
            self.env["geoengine.view.settings"].create(
                {"view_id": self.view.id} | settings
            )
        payload = self.env[self.view.model].get_layers(self.view.id)
        self.assertEqual(payload["projection"], "EPSG:3857")
        self.assertEqual(payload["default_map_zoom"], 7)
        self.assertIn("-13173896.5", payload["default_map_extent"])
        self.assertIn("20037508.3", payload["restricted_extent"])
