import logging
import time
import traceback
from contextlib import contextmanager
from threading import Lock
from typing import NamedTuple

import serial

from odoo.addons.iot_drivers.driver import Driver
from odoo.addons.iot_drivers.event_manager import event_manager

_logger = logging.getLogger(__name__)


class SerialProtocol(NamedTuple):
    name: any
    baudrate: any
    bytesize: any
    stopbits: any
    parity: any
    timeout: any
    writeTimeout: any
    measureRegexp: any
    statusRegexp: any
    commandTerminator: any
    commandDelay: any
    measureDelay: any
    newMeasureDelay: any
    measureCommand: any
    emptyAnswerValid: any


@contextmanager
def serial_connection(path, protocol, is_probing=False):

    PROBING_TIMEOUT = 1
    port_config = {
        "baudrate": protocol.baudrate,
        "bytesize": protocol.bytesize,
        "stopbits": protocol.stopbits,
        "parity": protocol.parity,
        "timeout": PROBING_TIMEOUT
        if is_probing
        else protocol.timeout,
        "writeTimeout": PROBING_TIMEOUT
        if is_probing
        else protocol.writeTimeout,
    }
    connection = serial.Serial(path, **port_config)
    try:
        yield connection
    finally:
        connection.close()


class SerialDriver(Driver):

    _protocol = None
    connection_type = "serial"

    STATUS_CONNECTED = "connected"
    STATUS_ERROR = "error"
    STATUS_CONNECTING = "connecting"
    STATUS_DISCONNECTED = "disconnected"

    def __init__(self, identifier, device) -> None:

        super().__init__(identifier, device)
        self._actions.update(
            {
                "get_status": self._push_status,
            }
        )
        self.device_connection = "serial"
        self._device_lock = Lock()
        self._status = {
            "status": self.STATUS_CONNECTING,
            "message_title": "",
            "message_body": "",
        }
        self._set_name()

    @staticmethod
    def _get_raw_response(connection):
        pass

    def _push_status(self) -> None:

        self.data["status"] = self._status

    def _set_name(self):

        try:
            name = ("%s serial %s" % (self._protocol.name, self.device_type)).title()
        except AttributeError:
            name = "Unknown Serial Device"
        self.device_name = name

    def _take_measure(self):
        pass

    def _do_action(self, data) -> None:

        with self._device_lock:
            try:
                self._actions[data["action"]](data)
                time.sleep(self._protocol.commandDelay)
                self._status = {
                    "status": self.STATUS_CONNECTED,
                    "message_title": "",
                    "message_body": "",
                }
            except Exception:
                msg = f'An error occurred while performing action "{data}" on "{self.device_name}"'
                _logger.exception(msg)
                self._status = {
                    "status": self.STATUS_ERROR,
                    "message_title": msg,
                    "message_body": traceback.format_exc(),
                }
            self._push_status()

    def action(self, data) -> None:
        self.data["owner"] = data.get("session_id")
        self.data["action_args"] = {**data}

        if self._connection and self._connection.isOpen():
            self._do_action(data)
        else:
            with serial_connection(
                self.device_identifier, self._protocol
            ) as connection:
                self._connection = connection
                self._do_action(data)
        event_manager.device_changed(
            self, data
        )

    def run(self):

        try:
            with serial_connection(
                self.device_identifier, self._protocol
            ) as connection:
                self._connection = connection
                self._status["status"] = self.STATUS_CONNECTED
                self._push_status()
                while not self._stopped.is_set():
                    self._take_measure()
                    time.sleep(self._protocol.newMeasureDelay)
                self._status["status"] = self.STATUS_DISCONNECTED
                self._push_status()
        except Exception:
            msg = "Error while reading %s" % self.device_name
            _logger.exception(msg)
            self._status = {
                "status": self.STATUS_ERROR,
                "message_title": msg,
                "message_body": traceback.format_exc(),
            }
            self._push_status()
