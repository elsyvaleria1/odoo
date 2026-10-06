"""Python half of the cross-runtime GS1 conformance suite.

The JS half is ``static/tests/gs1_conformance.test.js``; the vectors are
``static/tests/gs1_conformance_vectors.js``.
"""

import datetime
from pathlib import Path

from odoo.libs.json import loads as json_loads
from odoo.tests import common
from odoo.tools.misc import file_path

VECTORS_PATH = "barcodes_gs1_nomenclature/static/tests/gs1_conformance_vectors.js"
VECTORS_OPENING = "JSON.parse(String.raw`"


def load_vectors():
    source = Path(file_path(VECTORS_PATH)).read_text(encoding="utf-8")
    start = source.index(VECTORS_OPENING) + len(VECTORS_OPENING)
    return json_loads(source[start : source.index("`", start)])


class TestGs1Conformance(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vectors = load_vectors()

    def _nomenclature(self, rule_set, separator):
        nomenclature = self.env["barcode.nomenclature"].create(
            {
                "name": rule_set,
                "is_gs1_nomenclature": True,
                "gs1_separator_fnc1": separator,
            }
        )
        self.env["barcode.rule"].create(
            [
                {
                    "name": f"{rule_set} #{index}",
                    "barcode_nomenclature_id": nomenclature.id,
                    "encoding": "gs1-128",
                    **rule,
                }
                for index, rule in enumerate(self.vectors["rule_sets"][rule_set])
            ]
        )
        return nomenclature

    def test_gs1_conformance_vectors(self):
        for case in self.vectors["cases"]:
            nomenclature = self._nomenclature(case["rules"], case.get("separator"))
            with self.subTest(why=case["_why"], barcode=case["barcode"]):
                parts = nomenclature.parse_barcode(case["barcode"])
                if case["expected"] is None:
                    self.assertIsNone(parts)
                    continue
                self.assertEqual(
                    [
                        {
                            "type": part["type"],
                            "ai": part["ai"],
                            "value": part["value"].isoformat()
                            if isinstance(part["value"], datetime.date)
                            else part["value"],
                        }
                        for part in parts or []
                    ],
                    case["expected"],
                )

    def test_the_shipped_rule_set_is_the_installed_default(self):
        """The vectors' "shipped" rules are what the module installs, so the
        browser half reads the same nomenclature a database does."""
        installed = [
            {
                "sequence": rule.sequence,
                "pattern": rule.pattern,
                "type": rule.type,
                "gs1_content_type": rule.gs1_content_type,
                **({"gs1_decimal_usage": True} if rule.gs1_decimal_usage else {}),
            }
            for rule in self.env.ref(
                "barcodes_gs1_nomenclature.default_gs1_nomenclature"
            ).rule_ids.filtered(lambda r: r.encoding == "gs1-128")
        ]
        self.assertEqual(installed, self.vectors["rule_sets"]["shipped"])
