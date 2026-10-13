from odoo.exceptions import ValidationError
from odoo.tests import common


class TestBarcodeNomenclature(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nomenclature = cls.env["barcode.nomenclature"].create(
            {"name": "Barcode Nomenclature Test"}
        )

    def test_invalid_patterns_are_refused(self):
        rule = self.env["barcode.rule"].create(
            {
                "name": "Rule Test #1",
                "barcode_nomenclature_id": self.nomenclature.id,
                "encoding": "ean8",
            }
        )
        for pattern in (
            "......{}..",
            "......{DN}",
            "....{NN}{DD}",
            "*",
            "**>>>{ND}",
        ):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                rule.pattern = pattern
        rule.pattern = "..>>>{ND}"

    def test_a_sequence_change_reorders_the_next_parse(self):
        rule_a, _rule_b = self.env["barcode.rule"].create(
            [
                {
                    "name": "Rule A",
                    "barcode_nomenclature_id": self.nomenclature.id,
                    "encoding": "ean13",
                    "pattern": ".....{NNNDDDD}.",
                    "sequence": 3,
                },
                {
                    "name": "Rule B",
                    "barcode_nomenclature_id": self.nomenclature.id,
                    "encoding": "ean13",
                    "pattern": "22......{NNDD}.",
                    "sequence": 2,
                },
            ]
        )
        self.assertEqual(
            self.nomenclature.parse_barcode("2212345610259")["value"], 10.25
        )
        rule_a.sequence = 1
        result = self.nomenclature.parse_barcode("2212345610259")
        self.assertEqual(result["value"], 456.1025)
        self.assertEqual(result["base_code"], "2212300000002")
