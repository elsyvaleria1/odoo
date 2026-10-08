from unittest.mock import MagicMock, patch

from odoo.libs.json import loads, orjson_wrapper
from odoo.tests import BaseCase

stdlib_json = orjson_wrapper._json
_NO_STDLIB_READ = MagicMock(**{"loads.side_effect": AssertionError})


class TestJsonWideIntegers(BaseCase):
    def assertReadsLikeTheStdlib(self, text):
        value = loads(text)
        self.assertEqual(value, stdlib_json.loads(text))
        self.assertEqual(repr(value), repr(stdlib_json.loads(text)))

    def test_integers_past_64_bits_stay_exact(self):
        for text in (
            "18446744073709551616",
            "-9223372036854775809",
            '{"a": [1, {"b": 123456789012345678901234567890}]}',
            "[18446744073709551615, -9223372036854775808, 18446744073709551616]",
        ):
            with self.subTest(text=text):
                self.assertReadsLikeTheStdlib(text)

    def test_integers_within_64_bits_are_ints(self):
        self.assertEqual(
            loads("[18446744073709551615, -9223372036854775808]"),
            [18446744073709551615, -9223372036854775808],
        )

    def test_float_literals_stay_floats(self):
        for text in ("[1e19]", "[12345678901234567890.0]", '{"x": -1.5e300}'):
            with self.subTest(text=text):
                self.assertReadsLikeTheStdlib(text)

    def test_a_digit_run_inside_a_string_keeps_orjson_s_reading(self):
        text = '{"NoCertificado": "00001000000504465028", "total": 12.5}'
        with patch.object(orjson_wrapper, "_json", _NO_STDLIB_READ):
            self.assertEqual(
                loads(text), {"NoCertificado": "00001000000504465028", "total": 12.5}
            )

    def test_a_large_body_is_walked_not_scanned(self):
        blob = "7" * 25 + "x" * orjson_wrapper._BYTE_SCAN_LIMIT
        text = stdlib_json.dumps({"params": {"datas": blob, "n": 1}})
        with (
            patch.object(
                orjson_wrapper, "_has_wide_integer", side_effect=AssertionError
            ),
            patch.object(orjson_wrapper, "_json", _NO_STDLIB_READ),
        ):
            self.assertEqual(loads(text)["params"]["datas"], blob)

    def test_a_large_body_with_a_wide_integer_stays_exact(self):
        text = stdlib_json.dumps(
            {"pad": "x" * orjson_wrapper._BYTE_SCAN_LIMIT, "id": 2**70, "neg": -(2**64)}
        )
        self.assertReadsLikeTheStdlib(text)

    def test_a_body_past_the_walk_budget_falls_back_to_the_scan(self):
        rows = list(range(orjson_wrapper._WALK_BUDGET + 10))
        text = stdlib_json.dumps(
            {"pad": "x" * orjson_wrapper._BYTE_SCAN_LIMIT, "rows": rows + [2**65]}
        )
        self.assertReadsLikeTheStdlib(text)
        plain = stdlib_json.dumps(
            {"pad": "x" * orjson_wrapper._BYTE_SCAN_LIMIT, "rows": rows}
        )
        with patch.object(
            orjson_wrapper, "_has_wide_integer", wraps=orjson_wrapper._has_wide_integer
        ) as scan:
            self.assertEqual(loads(plain)["rows"], rows)
        scan.assert_called_once()
