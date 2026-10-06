import json
from datetime import datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import BaseCase, tagged

from odoo.addons.error_incident.tools import fingerprint as fp


def _raise_in_parse():
    datetime.strptime("not a date", "%Y-%m-%d")


def _raise_value_error(message="boom"):
    raise ValueError(message)


def _raise_value_error_elsewhere():
    raise ValueError("boom")


def _caught(function, *args):
    try:
        function(*args)
    except Exception as exc:
        return exc
    raise AssertionError("did not raise")


@tagged("post_install", "-at_install")
class TestFingerprint(BaseCase):
    def test_the_origin_is_our_frame_not_the_librarys(self):
        where = fp.origin(_caught(_raise_in_parse))
        self.assertEqual(where.module, "error_incident")
        self.assertEqual(where.path, "tests/test_fingerprint.py")
        self.assertEqual(where.function, "_raise_in_parse")

    def test_the_same_function_is_the_same_incident_whatever_the_line(self):
        first = fp.origin(_caught(_raise_value_error))
        moved = first._replace(line=first.line + 40)
        self.assertEqual(
            fp.fingerprint("ValueError", first), fp.fingerprint("ValueError", moved)
        )

    def test_another_function_or_exception_is_another_incident(self):
        here = fp.origin(_caught(_raise_value_error))
        there = fp.origin(_caught(_raise_value_error_elsewhere))
        self.assertNotEqual(
            fp.fingerprint("ValueError", here), fp.fingerprint("ValueError", there)
        )
        self.assertNotEqual(
            fp.fingerprint("ValueError", here), fp.fingerprint("KeyError", here)
        )

    def test_the_type_reads_as_a_traceback_prints_it(self):
        self.assertEqual(fp.exception_type(ValueError()), "ValueError")
        self.assertEqual(
            fp.exception_type(json.JSONDecodeError("x", "", 0)),
            "json.decoder.JSONDecodeError",
        )

    def test_errors_raised_for_the_user_are_not_defects(self):
        for exc in (UserError("x"), AccessError("x"), ValidationError("x")):
            self.assertTrue(fp.is_expected(exc), type(exc).__name__)
        self.assertFalse(fp.is_expected(ValueError("x")))
        self.assertFalse(fp.is_expected(KeyError("x")))
