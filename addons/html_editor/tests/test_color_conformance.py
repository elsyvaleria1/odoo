from pathlib import Path

from odoo.libs.json import loads as json_loads
from odoo.tests.common import BaseCase
from odoo.tools.misc import file_path

from odoo.addons.html_editor.models.ir_attachment import CSS_COLOR, parse_css_rgba

VECTORS_PATH = "html_editor/static/tests/color_conformance_vectors.js"
VECTORS_OPENING = "JSON.parse(String.raw`"


def load_vectors():
    source = Path(file_path(VECTORS_PATH)).read_text(encoding="utf-8")
    start = source.index(VECTORS_OPENING) + len(VECTORS_OPENING)
    return json_loads(source[start : source.index("`", start)])


class TestColorConformance(BaseCase):
    def test_conformance_vectors(self):
        for vector in load_vectors():
            value, rgba = vector["value"], vector["rgba"]
            with self.subTest(value=value):
                self.assertEqual(bool(CSS_COLOR.fullmatch(value)), rgba is not None)
                if rgba is None:
                    with self.assertRaises(ValueError):
                        parse_css_rgba(value)
                else:
                    self.assertEqual(list(parse_css_rgba(value)), rgba)
