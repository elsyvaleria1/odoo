import logging
import pprint
import sys
import time

from odoo.libs.json import dumps as json_dumps
from odoo.tests import BaseCase, tagged

from odoo.addons.payment.logging import SensitiveDataFilter

MASK = "***REDACTED***"


@tagged("-at_install", "post_install")
class TestSensitiveDataFilter(BaseCase):
    def _record(self, filter_, msg, *args, exc_info=None, sinfo=None):
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, msg, args, exc_info, sinfo=sinfo
        )
        self.assertTrue(filter_.filter(record))
        return record

    def _emitted(self, filter_, msg, *args, exc_info=None, sinfo=None):
        record = self._record(filter_, msg, *args, exc_info=exc_info, sinfo=sinfo)
        return logging.Formatter("%(message)s").format(record)

    def test_a_secret_is_masked_without_any_provider_key(self):
        event = {
            "data": {
                "object": {
                    "id": "pi_3Mtw",
                    "client_secret": "pi_3Mtw_secret_YrKJUKribc",
                    "metadata": {"api_key": "sk_live_51H8abcdefghij"},
                    "card": {"last4": "4242"},
                }
            }
        }
        filter_ = SensitiveDataFilter()
        for msg, args in (
            ("Notification received with data:\n%s", (pprint.pformat(event),)),
            ("payload %s", (json_dumps(event),)),
            ("payload %s", (event,)),
            (f"payload {event}", ()),
        ):
            with self.subTest(msg=msg):
                emitted = self._emitted(filter_, msg, *args)
                self.assertNotIn("YrKJUKribc", emitted)
                self.assertNotIn("sk_live_51H8", emitted)
                self.assertIn("pi_3Mtw", emitted)
                self.assertIn("4242", emitted)

    def test_a_provider_key_is_masked_whatever_its_value_s_shape(self):
        filter_ = SensitiveDataFilter({"a.b[c]"})
        for text in (
            '{"a.b[c]": "abc"}',
            "{'a.b[c]': 'abc'}",
            '{"a.b[c]": 123456}',
            "a.b[c]=abc&n=1",
            '{"a.b[c]": "ab\\"c"}',
        ):
            with self.subTest(text=text):
                emitted = self._emitted(filter_, "%s", text)
                self.assertNotIn("abc", emitted)
                self.assertNotIn("123456", emitted)
                self.assertIn(MASK, emitted)

    def test_a_provider_key_inside_a_longer_name_is_not_it(self):
        emitted = self._emitted(
            SensitiveDataFilter({"ref"}), "%s", "{'tx_ref': 'S001'}"
        )
        self.assertIn("S001", emitted)

    def test_masking_twice_changes_nothing(self):
        filter_ = SensitiveDataFilter({"cvx"})
        once = self._emitted(filter_, "%s", "{'cvx': 'xyz', 'api_key': 'sk_1abc'}")
        self.assertEqual(self._emitted(filter_, once), once)

    def test_a_key_added_to_the_shared_set_later_is_masked(self):
        keys = set()
        filter_ = SensitiveDataFilter(keys)
        self.assertIn("xyz", self._emitted(filter_, "%s", "{'cvx': 'xyz'}"))
        keys.add("cvx")
        self.assertNotIn("xyz", self._emitted(filter_, "%s", "{'cvx': 'xyz'}"))

    def test_the_traceback_is_masked_too(self):
        try:
            raise ValueError("refused: {'api_key': 'sk_live_51H8abcdefghij'}")
        except ValueError as error:
            exc_info = (type(error), error, error.__traceback__)
        emitted = self._emitted(SensitiveDataFilter(), "call failed", exc_info=exc_info)
        self.assertIn("ValueError", emitted)
        self.assertNotIn("sk_live_51H8", emitted)

    def test_a_record_that_cannot_format_says_so_in_its_message(self):
        record = self._record(SensitiveDataFilter(), "%d", "x")
        self.assertEqual(record.args, ())
        self.assertEqual(record.getMessage(), "%d [unformattable args: ('x',)]")

    def test_a_provider_key_s_value_is_masked_whatever_its_type(self):
        filter_ = SensitiveDataFilter({"card_data"})
        for value in (
            {"number": "4111111111111111", "cvc": "123"},
            ["4111111111111111", "123"],
            ("4111111111111111", "123"),
            {"4111111111111111"},
            b"4111111111111111",
            4111111111111111,
        ):
            for msg, args in (
                ("%s", ({"card_data": value, "ref": "S1"},)),
                ("%s %s", ("S1", [{"card_data": value}])),
                ("%(card_data)s", ({"card_data": value},)),
                ("%s", (pprint.pformat({"card_data": value, "ref": "S1"}),)),
            ):
                with self.subTest(value=value, msg=msg, args=args):
                    emitted = self._emitted(filter_, msg, *args)
                    self.assertNotIn("4111", emitted)
                    self.assertNotIn("123", emitted)
                    self.assertIn(MASK, emitted)

    def test_a_masked_value_keeps_the_structure_around_it(self):
        filter_ = SensitiveDataFilter({"client_secret", "cvx"})
        for text, emitted in (
            (
                '{"client_secret": 123456, "amount": 1}',
                f'{{"client_secret": {MASK}, "amount": 1}}',
            ),
            ("{'x': [{'cvx': 123}]}", f"{{'x': [{{'cvx': {MASK}}}]}}"),
            ("{'cvx': {'n': 1}, 'ref': 'S1'}", f"{{'cvx': {MASK}, 'ref': 'S1'}}"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self._emitted(filter_, "%s", text), emitted)

    def test_a_literal_under_a_secret_name_is_kept(self):
        literals = {"isNewToken": True, "tokenize": False, "token": None}
        for text in (pprint.pformat(literals), json_dumps(literals)):
            with self.subTest(text=text):
                self.assertEqual(self._emitted(SensitiveDataFilter(), "%s", text), text)

    def test_a_masked_card_label_is_kept_and_a_signature_masked(self):
        notification = {
            "additionalData": {
                "authCode": "083210",
                "hmacSignature": "VcoiMGe4ClMsMhLlgSOgZRZMBNqaVh1NfTTn+vAuXa8=",
            },
            "pspReference": "8816178914079738",
        }
        emitted = self._emitted(
            SensitiveDataFilter(),
            "token_name=%s notification:\n%s",
            "•••• 4242",
            pprint.pformat(notification),
        )
        self.assertIn("token_name=•••• 4242", emitted)
        self.assertNotIn("VcoiMGe4", emitted)
        self.assertNotIn("083210", emitted)
        self.assertIn("8816178914079738", emitted)

    def test_a_long_message_is_cut_and_its_cost_bounded(self):
        filter_ = SensitiveDataFilter()
        event = {"api_key": "sk_live_51H8abcdefghij", "reference": "S1"}

        def mask(count):
            payload = pprint.pformat([event] * count)
            best = float("inf")
            for _attempt in range(3):
                start = time.process_time()
                emitted = self._emitted(filter_, "payload %s", payload)
                best = min(best, time.process_time() - start)
            return emitted, max(best, 1e-3)

        _emitted, small = mask(2_000)
        emitted, large = mask(20_000)
        self.assertLess(large, 3 * small)
        self.assertLess(len(emitted), 70_000)
        self.assertRegex(emitted, r"\.\.\. \[\d+ more characters not logged\]$")
        self.assertNotIn("sk_live_51H8", emitted)

    def test_the_raw_exception_does_not_outlive_its_masked_traceback(self):
        try:
            raise ValueError("refused: {'api_key': 'sk_live_51H8abcdefghij'}")
        except ValueError as error:
            exc_info = (type(error), error, error.__traceback__)
        record = self._record(SensitiveDataFilter(), "call failed", exc_info=exc_info)
        self.assertIsNone(record.exc_info)
        self.assertIn("ValueError", record.exc_text)
        self.assertNotIn("sk_live_51H8", record.exc_text)
        self.assertIn("ValueError", logging.Formatter().format(record))

    def test_the_stack_is_masked_too(self):
        emitted = self._emitted(
            SensitiveDataFilter(),
            "where",
            sinfo='Stack (most recent call last):\n  call(password="hunter2")',
        )
        self.assertIn("Stack", emitted)
        self.assertNotIn("hunter2", emitted)

    def test_a_record_with_nothing_to_mask_keeps_its_message_and_args(self):
        record = self._record(SensitiveDataFilter({"cvx"}), "tx %s: %s", "S1", 100)
        self.assertEqual((record.msg, record.args), ("tx %s: %s", ("S1", 100)))

    def test_every_payment_module_logger_masks(self):
        unmasked = [
            name
            for name, module in list(sys.modules.items())
            if name.startswith("odoo.addons.payment")
            and ".tests" not in name
            and isinstance(logger := getattr(module, "_logger", None), logging.Logger)
            and not any(isinstance(f, SensitiveDataFilter) for f in logger.filters)
        ]
        self.assertEqual(unmasked, [])

    def test_args_that_cannot_be_walked_do_not_raise_into_the_caller(self):
        class Unwalkable(dict):
            def items(self):
                raise RuntimeError("cannot be walked")

            def __iter__(self):
                raise RuntimeError("cannot be walked")

        emitted = self._emitted(
            SensitiveDataFilter({"cvx"}), "%s %s", Unwalkable(), "api_key=sk_1abc"
        )
        self.assertNotIn("sk_1abc", emitted)

    def test_args_that_cannot_be_formatted_are_masked_not_dumped(self):
        class Unwalkable(dict):
            def items(self):
                raise RuntimeError("cannot be walked")

        record = self._record(
            SensitiveDataFilter({"merchant_secret"}),
            "two %s %s",
            Unwalkable(merchant_secret="hunter2"),
        )
        self.assertEqual(record.args, ())
        self.assertNotIn("hunter2", record.getMessage())

    def test_a_message_that_cannot_render_at_all_raises_nothing(self):
        class Unrenderable:
            def __str__(self):
                raise RuntimeError("no str")

            __repr__ = __str__

        record = self._record(SensitiveDataFilter(), Unrenderable(), 1)
        self.assertEqual(
            record.getMessage(),
            "<unformattable Unrenderable message> [unformattable args: (1,)]",
        )
        record = self._record(SensitiveDataFilter(), Unrenderable())
        self.assertEqual(record.getMessage(), "<unformattable Unrenderable message>")

    def test_a_message_keeps_its_text_when_only_its_args_fail(self):
        class Unrenderable:
            def __int__(self):
                raise RuntimeError("no int")

            def __repr__(self):
                raise RuntimeError("no repr")

        record = self._record(
            SensitiveDataFilter(), "charge %d for password=hunter2", Unrenderable()
        )
        self.assertEqual(
            record.getMessage(),
            f"charge %d for password={MASK} [unformattable args]",
        )

    def test_a_record_that_cannot_be_masked_is_emptied_not_raised(self):
        record = self._record(
            SensitiveDataFilter(), "token=%s", "hunter2", exc_info=("malformed",)
        )
        self.assertNotIn("hunter2", record.getMessage())
        self.assertIn("masking it failed", record.getMessage())
        self.assertIsNone(record.exc_info)

    def test_a_card_number_under_no_key_keeps_only_its_last_four(self):
        emitted = self._emitted(
            SensitiveDataFilter(),
            "charge %s, card 4111 1111 1111 1111, order 1234567890123",
            "4242-4242-4242-4242",
        )
        self.assertEqual(emitted, "charge ****4242, card ****1111, order 1234567890123")

    def test_a_secret_named_only_by_its_mapping_key_is_masked(self):
        emitted = self._emitted(
            SensitiveDataFilter(),
            "login %(user)s with %(password)s",
            {"user": "bob", "password": "hunter2"},
        )
        self.assertEqual(emitted, f"login bob with {MASK}")

    def test_a_provider_key_that_is_no_string_still_masks(self):
        emitted = self._emitted(SensitiveDataFilter({1}), "%s", {"1": "secretvalue"})
        self.assertNotIn("secretvalue", emitted)
