import logging
import unittest

from odoo.libs.debug_log import DebugLog


class DebugLogTests(unittest.TestCase):
    def test_timing_preserves_binding_result_and_disabled_behavior(self) -> None:
        debug = DebugLog("typing_contracts")

        @debug.perf.timed
        def describe(value: int, /, *, label: str = "") -> str:
            return f"{label}{value}"

        logger = debug.perf.logger
        previous = logger.level
        try:
            logger.setLevel(logging.WARNING)
            self.assertEqual(describe(3, label="value="), "value=3")
            with debug.perf("disabled") as span:
                span.set(count=3)
            with self.assertRaises(TypeError):
                describe(3, "label")  # type: ignore[call-arg]  # Check runtime keyword-only binding.
            with self.assertLogs(logger, level=logging.DEBUG) as captured:
                self.assertEqual(describe(4, label="value="), "value=4")
            self.assertEqual(len(captured.records), 1)
            self.assertIn("event=describe", captured.records[0].getMessage())
            self.assertEqual(describe.__name__, "describe")
        finally:
            logger.setLevel(previous)

    def test_event_and_span_channels_keep_their_result_contracts(self) -> None:
        debug = DebugLog("typing_contracts")
        with self.assertLogs(debug.logic.logger, level=logging.DEBUG) as captured:
            self.assertIsNone(debug.logic("event", count=3))  # type: ignore[func-returns-value]  # Verify the runtime None contract.
        self.assertIn("event=event", captured.records[0].getMessage())
        with self.assertLogs(debug.perf.logger, level=logging.DEBUG) as captured:
            self.assertIsNone(debug.perf.count("counted", count=3))  # type: ignore[func-returns-value]  # Verify the runtime None contract.
            with self.assertRaisesRegex(ValueError, "failure"):
                with debug.perf("span") as span:
                    span.set(count=4)
                    raise ValueError("failure")
        self.assertEqual(len(captured.records), 2)
        self.assertIn("error=ValueError", captured.records[1].getMessage())
