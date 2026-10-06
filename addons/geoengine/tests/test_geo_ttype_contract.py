import pathlib
import re

from odoo.tests import TransactionCase, tagged

from ..models.geo_types import GEO_FIELD_TTYPES

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent

CLIENT_COPIES = {
    "static/src/fields/geo_form_field.js": "GEO_TYPES",
}

_STRING = re.compile(r'"([^"]*)"')


def read_client_list(relative_path: str, name: str) -> list[str]:
    source = (MODULE_ROOT / relative_path).read_text()
    match = re.search(rf"const {name} = \[(.*?)\];", source, re.DOTALL)
    if not match:
        raise ValueError(
            f"{relative_path} no longer declares `const {name} = [...]`; teach "
            "this contract the new shape rather than leaving the copy unpinned."
        )
    return _STRING.findall(match.group(1))


@tagged("post_install", "-at_install")
class TestGeoTtypeContract(TransactionCase):
    def test_the_client_copies_match_the_canonical_tuple(self):
        for relative_path, name in CLIENT_COPIES.items():
            with self.subTest(file=relative_path):
                self.assertEqual(
                    read_client_list(relative_path, name),
                    list(GEO_FIELD_TTYPES),
                    f"{relative_path} keeps its own copy of the geometry ttype "
                    "list because it cannot import the Python constant. Adding a "
                    "geometry type to models/geo_types.py without adding it here "
                    "leaves the client blind to it, silently.",
                )

    def test_the_reader_would_notice_a_drifted_copy(self):
        self.assertEqual(
            _STRING.findall('const X = ["geo_point", "geo_line"];'),
            ["geo_point", "geo_line"],
        )
        with self.assertRaises(ValueError):
            read_client_list("static/src/fields/geo_form_field.js", "NO_SUCH_LIST")
