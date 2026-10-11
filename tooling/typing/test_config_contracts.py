import importlib
import inspect
import logging
import unittest
import warnings
from unittest.mock import patch

from odoo.tools.config import _CountingDict, configmanager


class ConfigurationContractTests(unittest.TestCase):
    def test_warning_locations_match_direct_warning_calls(self) -> None:
        class Config(configmanager):
            _log_entries = []
            _warn_entries = []

        Config._flush_log_and_warn_entries()
        configuration = importlib.import_module("odoo.tools.config")
        assert configuration.__file__ is not None

        def emit(
            *, wrapped: bool, level: int, prefixes: tuple[str, ...]
        ) -> tuple[str, int]:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                warn = Config._warn if wrapped else warnings.warn
                warn("location", stacklevel=level, skip_file_prefixes=prefixes)
            return caught[-1].filename, caught[-1].lineno

        for level in (-2, 0, 1, 2, 3):
            for prefixes in ((), (configuration.__file__,), (__file__,)):
                with self.subTest(stacklevel=level, prefixes=prefixes):
                    # The calls share their source line, so every level agrees.
                    direct, wrapped = (
                        emit(wrapped=value, level=level, prefixes=prefixes)
                        for value in (False, True)
                    )
                    self.assertEqual(direct, wrapped)

    def test_log_locations_match_direct_logger_calls(self) -> None:
        class Config(configmanager):
            _log_entries = []
            _warn_entries = []

        Config._flush_log_and_warn_entries()
        logger = logging.getLogger("odoo.tools.config")

        def emit(*, wrapped: bool, level: int) -> tuple[str, int]:
            with self.assertLogs(logger, level="INFO") as caught:
                log = Config._log if wrapped else logger.log
                log(logging.INFO, "location", stacklevel=level)
            return caught.records[-1].pathname, caught.records[-1].lineno

        for level in (0, 1, 2, 3):
            with self.subTest(stacklevel=level):
                direct, wrapped = (
                    emit(wrapped=value, level=level) for value in (False, True)
                )
                self.assertEqual(direct, wrapped)

    def test_inplace_updates_invalidate_once_and_keep_identity(self) -> None:
        generations = []
        options = _CountingDict(lambda: generations.append(len(generations)))
        original = options
        options |= {"first": 1, "second": 2}
        self.assertIs(options, original)
        self.assertEqual(dict(options), {"first": 1, "second": 2})
        self.assertEqual(generations, [0])

    def test_buffered_messages_flush_once_and_keep_native_callbacks(self) -> None:
        class Config(configmanager):
            _log_entries = []
            _warn_entries = []

        with patch("odoo.tools.config._dangerous_logger") as logger:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                Config._log(20, "buffered %s", "log")
                Config._warn("buffered warning", UserWarning)
                self.assertEqual(len(caught), 0)
                logger.log.assert_not_called()
                Config._flush_log_and_warn_entries()
                Config._flush_log_and_warn_entries()
                self.assertEqual([str(w.message) for w in caught], ["buffered warning"])
                logger.log.assert_called_once_with(20, "buffered %s", "log")
                Config._log(20, "direct log")
                Config._warn("direct warning", UserWarning)
                self.assertEqual(str(caught[-1].message), "direct warning")
                self.assertEqual(caught[-1].filename, __file__)
                self.assertEqual(logger.log.call_args.args, (20, "direct log"))
        self.assertIs(Config._warn, warnings.warn)

    def test_explicit_warning_stacklevels(self) -> None:
        class Config(configmanager):
            _log_entries = []
            _warn_entries = []

        Config._flush_log_and_warn_entries()

        def warn(*, positional: bool) -> None:
            if positional:
                Config._warn("positional", UserWarning, 2)
            else:
                Config._warn("keyword", UserWarning, stacklevel=2)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = inspect.currentframe()
            assert frame is not None
            line = frame.f_lineno + 1
            warn(positional=True)
            self.assertEqual(caught[-1].lineno, line)
            line = frame.f_lineno + 1
            warn(positional=False)
            self.assertEqual(caught[-1].lineno, line)
