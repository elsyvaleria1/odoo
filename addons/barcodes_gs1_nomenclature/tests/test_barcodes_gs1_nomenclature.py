from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tests.common import TransactionCase


class TestBarcodeGS1Nomenclature(TransactionCase):
    PADDED_1236 = [
        "1236",
        "00001236",
        "000000001236",
        "0000000001236",
        "00000000001236",
        "000000000000001236",
    ]

    def test_invalid_fnc1_separator_raises_validation_error(self):
        nomenclature = self.env["barcode.nomenclature"].create(
            {
                "name": "Test GS1 invalid separator",
                "is_gs1_nomenclature": True,
            }
        )
        with self.assertRaises(ValidationError):
            nomenclature.gs1_separator_fnc1 = "("

    def test_fnc1_separator_is_held_to_browser_syntax(self):
        nomenclature = self.env["barcode.nomenclature"].create(
            {"name": "Test GS1 separator syntax", "is_gs1_nomenclature": True}
        )
        for separator in ("(?i)alt029", "\\Z", "[]#]"):
            with self.subTest(separator=separator), self.assertRaises(ValidationError):
                nomenclature.gs1_separator_fnc1 = separator
        nomenclature.gs1_separator_fnc1 = "(Alt029|#|\\x1D)"

    def test_preprocess_gs1_search_args_product(self):
        company = self.env.company
        company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        domain = [("barcode", "in", [])]
        res = self.env["barcode.nomenclature"]._preprocess_gs1_search_args(
            domain, ["product"]
        )
        self.assertEqual(res, Domain(domain))

    def test_exact_gs1_search_stays_exact(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        preprocess = self.env["barcode.nomenclature"]._preprocess_gs1_search_args
        scan = "0100000000001236"
        padded = self.PADDED_1236
        self.assertEqual(
            preprocess([("barcode", "=", scan)], ["product"]),
            Domain("barcode", "in", padded),
        )
        self.assertEqual(
            preprocess([("barcode", "!=", scan)], ["product"]),
            Domain("barcode", "not in", padded),
        )
        self.assertEqual(
            preprocess([("barcode", "ilike", scan)], ["product"]),
            Domain("barcode", "ilike", "1236"),
        )
        self.assertEqual(
            preprocess([("barcode", "=", "0001236")], ["product"]),
            Domain("barcode", "in", padded),
        )

    def test_a_non_text_barcode_search_is_left_to_the_orm(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        preprocess = self.env["barcode.nomenclature"]._preprocess_gs1_search_args
        for condition in (("barcode", "=", 123), ("barcode", "!=", 1236.0)):
            with self.subTest(condition=condition):
                self.assertEqual(
                    preprocess([condition], ["product"]), Domain(*condition)
                )
        self.assertEqual(
            preprocess([("barcode", "in", ["0100000000001236", 77])], ["product"]),
            Domain("barcode", "in", self.PADDED_1236) | Domain("barcode", "=", 77),
        )

    def test_gs1_rule_patterns_are_held_to_the_shared_checks(self):
        nomenclature = self.env["barcode.nomenclature"].create(
            {"name": "GS1 checks", "is_gs1_nomenclature": True}
        )

        def add_rule(pattern):
            return self.env["barcode.rule"].create(
                {
                    "name": pattern,
                    "barcode_nomenclature_id": nomenclature.id,
                    "encoding": "gs1-128",
                    "type": "lot",
                    "gs1_content_type": "alpha",
                    "pattern": pattern,
                }
            )

        for pattern in ("(10)((?:a+)+)b", "(10)((\\d{2,})+)", "(?P<ai>10)(.*)"):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                add_rule(pattern)
        self.assertTrue(add_rule("(30)(\\d{0,8})"))
