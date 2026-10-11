import contextlib
import logging
import queue
import threading
import time

import requests

from odoo.logutils import ColoredFormatter

from odoo.addons.iot_drivers.tools import helpers
from odoo.addons.iot_drivers.tools.system import IS_TEST

_logger = logging.getLogger(__name__)

IOT_LOG_TO_SERVER_CONFIG_NAME = "iot_log_to_server"


class AsyncHTTPHandler(logging.Handler):

    _MAX_QUEUE_SIZE = 1000
    """Maximum queue size. If a log record is received but the queue if full it will be discarded"""
    _MAX_BATCH_SIZE = 50
    """Maximum number of sent logs batched at once. Used to avoid too heavy request. Log records still in the queue will
    be handle in future flushes"""
    _FLUSH_INTERVAL = 0.5
    """How much seconds it will sleep before checking for new logs to send"""
    _REQUEST_TIMEOUT = 10
    """Amount of seconds to wait per log to send before timeout"""
    _DELAY_BEFORE_NO_SERVER_LOG = 5 * 60
    """Minimum delay in seconds before we log a server disconnection.
    Used in order to avoid the IoT log file to have a log recorded each _FLUSH_INTERVAL (as this value is very small)"""

    def __init__(self, odoo_server_url, active) -> None:
        super().__init__()
        self._odoo_server_url = odoo_server_url
        self._db_name = helpers.get_conf("db_name") or ""
        self._log_queue = queue.Queue(self._MAX_QUEUE_SIZE)
        self._flush_thread = None
        self._active = None
        self._next_disconnection_time = None
        self.toggle_active(active)

    def toggle_active(self, is_active) -> None:
        self._active = is_active
        if self._active and self._odoo_server_url:
            self._flush_thread = threading.Thread(
                target=self._periodic_flush, name="ThreadServerLogSender", daemon=True
            )
            self._flush_thread.start()
        else:
            self._flush_thread and self._flush_thread.join()

    def _periodic_flush(self) -> None:
        odoo_session = requests.Session()
        while (
            self._odoo_server_url and self._active
        ):
            time.sleep(self._FLUSH_INTERVAL)
            self._flush_logs(odoo_session)

    def _flush_logs(self, odoo_session) -> None:
        def convert_to_byte(s):
            return bytes(s, encoding="utf-8") + b"<log/>\n"

        def convert_server_line(log_level, line_formatted):
            return convert_to_byte(f"{log_level},{line_formatted}")

        def empty_queue():
            yield convert_to_byte(f"identifier {helpers.get_identifier()}")
            for _ in range(self._MAX_BATCH_SIZE):
                try:
                    log_record = self._log_queue.get_nowait()
                    yield convert_server_line(
                        log_record.levelno, self.format(log_record)
                    )
                except queue.Empty:
                    break

            if queue_size >= 0.8 * self._MAX_QUEUE_SIZE:
                log_message = (
                    f"The IoT {self.__class__.__name__} queue is saturating: "
                    f"{queue_size}/{self._MAX_QUEUE_SIZE} "
                    f"({100 * queue_size / self._MAX_QUEUE_SIZE:.2f}%)"
                )
                _logger.warning(
                    log_message
                )
                yield convert_server_line(logging.WARNING, log_message)

        queue_size = self._log_queue.qsize()

        if not self._odoo_server_url or queue_size == 0:
            return
        try:
            odoo_session.post(
                self._odoo_server_url + "/iot/log",
                data=empty_queue(),
                headers={"X-Odoo-Database": self._db_name},
                timeout=self._REQUEST_TIMEOUT,
            ).raise_for_status()
            self._next_disconnection_time = None
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
        ) as request_errors:
            now = time.time()
            if (
                not self._next_disconnection_time
                or now >= self._next_disconnection_time
            ):
                _logger.info(
                    "Connection with the server to send the logs failed. It is likely down: %s",
                    request_errors,
                )
                self._next_disconnection_time = now + self._DELAY_BEFORE_NO_SERVER_LOG
        except Exception:
            _logger.exception("Unexpected error happened while sending logs to server")

    def emit(self, record) -> None:
        if not self._active:
            return
        with contextlib.suppress(queue.Full):
            self._log_queue.put_nowait(record)

    def close(self):
        self.toggle_active(False)
        super().close()


def close_server_log_sender_handler() -> None:
    _server_log_sender_handler.close()


def get_odoo_config_log_to_server_option():
    return not IS_TEST and (
        helpers.get_conf(IOT_LOG_TO_SERVER_CONFIG_NAME, section="options") or True
    )


def check_and_update_odoo_config_log_to_server_option(new_state) -> bool:
    if get_odoo_config_log_to_server_option() != new_state:
        helpers.update_conf(
            {IOT_LOG_TO_SERVER_CONFIG_NAME, new_state}, section="options"
        )
        _server_log_sender_handler.toggle_active(new_state)
        return True
    return False


def _server_log_sender_handler_filter(log_record) -> bool:
    def _filter_my_logs():
        return log_record.name == __name__

    def _filter_frequent_irrelevant_calls():
        return (
            log_record.name == "odoo.service.http.access"
            and log_record.args
            and len(log_record.args) > 0
            and str(log_record.args[0]).startswith("GET /hw_proxy/hello ")
        )

    return not (_filter_my_logs() or _filter_frequent_irrelevant_calls())


_server_log_sender_handler = AsyncHTTPHandler(
    helpers.get_odoo_server_url(), get_odoo_config_log_to_server_option()
)
if not IS_TEST:
    _server_log_sender_handler.setFormatter(
        ColoredFormatter(
            "%(asctime)s %(pid)s %(levelname)s %(dbname)s %(name)s: %(message)s %(perf_info)s"
        )
    )
    _server_log_sender_handler.addFilter(_server_log_sender_handler_filter)
    logging.getLogger().addHandler(_server_log_sender_handler)
