"""Regression tests for the ways scanned input used to reach a 500.

`parse_barcode` is reachable over RPC by any internal user and its argument is
whatever came off a scanner, so a malformed barcode has to be a parse failure --
never an exception, and never unbounded work.
"""

from odoo.exceptions import ValidationError
from odoo.tests import common


class TestBarcodeHardening(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nomenclature = cls.env["barcode.nomenclature"].create(
            {"name": "Hardening Test"}
        )

    def _add_rule(self, **vals):
        return self.env["barcode.rule"].create(
            {
                "name": "Rule",
                "barcode_nomenclature_id": self.nomenclature.id,
                "encoding": "any",
                "type": "product",
                **vals,
            }
        )

    def test_malformed_uri_is_a_parse_failure(self):
        for barcode in (
            "urn:epc:id:sgtin:4012345.012345",
            "urn:epc:id:sgtin:4012345.012345.99.88",
            "urn:epc:id:sscc:952656789012",
            "urn:epc:id:giai:4012345.999887",
            "urn:",
            "urn:epc:id:sscc:abcdefghijkl.03456",
        ):
            with self.subTest(barcode=barcode):
                self.assertEqual(self.nomenclature.parse_barcode(barcode), [])

    def test_non_digit_numeric_slot_is_a_parse_failure(self):
        self._add_rule(pattern="21{NNDDD}")
        for barcode in ("21²²²²²", "21123ab", "2112", "21"):
            with self.subTest(barcode=barcode):
                result = self.nomenclature.parse_barcode(barcode)
                self.assertEqual(result["type"], "error")
                self.assertEqual(result["value"], 0)
        self.assertEqual(self.nomenclature.parse_barcode("2112345")["value"], 12.345)

    def test_catastrophic_pattern_is_rejected(self):
        for pattern in (
            "(x+x+)+y",
            "(a+)*",
            "(?:a+)+",
            "([a-z]+)*$",
            "(\\d+)+",
            "(a|aa)+$",
        ):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                self._add_rule(pattern=pattern)

    def test_ordinary_patterns_are_still_accepted(self):
        for pattern in (
            ".*",
            "^[0-9]+$",
            "21.....{NNDDD}",
            "23.....{NNNDD}",
            "22{NN}",
            "(A|B)+",
            "O-BTN.pack",
            "414",
        ):
            with self.subTest(pattern=pattern):
                self.assertTrue(self._add_rule(pattern=pattern))

    def test_python_only_syntax_is_rejected(self):
        for pattern in (
            "(?P<ai>21).*",
            "a++",
            "a?+",
            "(?>a)b",
            "21\\Z",
            "\\A21",
            "(?i)abc",
            "(?#note)21",
            "21\\z",
            "\\a",
            "\\U00000041",
            "[]a]",
            "[^]a]",
            "[[a]",
            "[a--b]",
            "(?<=2)*1",
            "(?=2)?2",
        ):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                self._add_rule(pattern=pattern)

    def test_portable_syntax_is_accepted(self):
        for pattern in (
            "21(?=3)",
            "(?<=2)1",
            "(?:21|22)3",
            "[?+*]+x",
            "\\d+?",
            "\\++",
            "(a)\\1",
            "\\\\{NN}",
            "\\\\1{NN}",
        ):
            with self.subTest(pattern=pattern):
                self.assertTrue(self._add_rule(pattern=pattern))

    def test_shorthand_classes_are_ascii_as_in_the_browser(self):
        self._add_rule(pattern="\\d+")
        self.assertEqual(self.nomenclature.parse_barcode("\u0663")["type"], "error")
        self.assertEqual(self.nomenclature.parse_barcode("3")["type"], "product")

    def test_numbered_backreference_is_rejected_beside_a_value(self):
        with self.assertRaises(ValidationError):
            self._add_rule(pattern="{NN}(a)\\1")

    def test_oversized_barcode_is_not_matched(self):
        self._add_rule(pattern=".*")
        result = self.nomenclature.parse_barcode("x" * 5000)
        self.assertEqual(result["type"], "error")

    def test_parse_barcode_refuses_multiple_nomenclatures(self):
        other = self.env["barcode.nomenclature"].create({"name": "Other"})
        with self.assertRaises(ValueError):
            (self.nomenclature | other).parse_barcode("12345670")

    def test_alias_rule_requires_an_alias(self):
        with self.assertRaises(ValidationError):
            self._add_rule(type="alias", pattern="^AAA", alias=False)


class TestBarcodeSessionInfo(common.TransactionCase):
    """`session_info` is on the critical path of every backend page load.

    An administrator who cleared the parameter in the UI stored an empty
    string -- which `get_param`'s default does not cover -- and every internal
    user got an HTTP 500 on /odoo until someone guessed why.
    """

    def _max_time(self, raw):
        self.env["ir.config_parameter"].sudo().set_param(
            "barcode.max_time_between_keys_in_ms", raw
        )
        return self.env["ir.http"]._get_max_time_between_keys()

    def test_invalid_parameter_falls_back(self):
        for raw in ("", "fast", "150.5", "   "):
            with self.subTest(raw=raw):
                self.assertEqual(self._max_time(raw), 150)

    def test_out_of_range_parameter_is_floored(self):
        for raw in ("0", "-5"):
            with self.subTest(raw=raw):
                self.assertEqual(self._max_time(raw), 1)

    def test_valid_parameter_is_used(self):
        self.assertEqual(self._max_time("  220  "), 220)

    def test_absent_parameter_uses_the_default(self):
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "barcode.max_time_between_keys_in_ms")]
        ).unlink()
        self.assertEqual(self.env["ir.http"]._get_max_time_between_keys(), 150)
