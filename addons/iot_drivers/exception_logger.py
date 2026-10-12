import logging
import sys
from io import StringIO

from odoo.addons.iot_drivers.tools.system import IS_TEST

_logger = logging.getLogger(__name__)


class ExceptionLogger:
    def __init__(self) -> None:
        self._buffer = StringIO()

    def write(self, message):
        self._buffer.write(message)
        if message.endswith("\n"):
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        self._buffer.seek(0)
        _logger.error(self._buffer.getvalue().rstrip("\n"))
        self._buffer = StringIO()

    def flush(self) -> None:
        if self._buffer.tell() > 0:
            self._flush_buffer()

    def close(self):
        self.flush()


if not IS_TEST:
    sys.stderr = ExceptionLogger()
