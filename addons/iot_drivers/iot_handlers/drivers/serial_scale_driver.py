import logging
import re
import threading
import time

import serial

from odoo import http

from odoo.addons.iot_drivers.controllers.proxy import proxy_drivers
from odoo.addons.iot_drivers.event_manager import event_manager
from odoo.addons.iot_drivers.iot_handlers.drivers.serial_base_driver import (
    SerialDriver,
    SerialProtocol,
    serial_connection,
)

_logger = logging.getLogger(__name__)

ACTIVE_SCALE = None
new_weight_event = threading.Event()

Toledo8217Protocol = SerialProtocol(
    name="Toledo 8217",
    baudrate=9600,
    bytesize=serial.SEVENBITS,
    stopbits=serial.STOPBITS_ONE,
    parity=serial.PARITY_EVEN,
    timeout=1,
    writeTimeout=1,
    measureRegexp=b"\x02\\s*([0-9.]+)N?\\r",
    statusRegexp=b"\x02\\s*\\?([^\x00])\\r",
    commandDelay=0.2,
    measureDelay=0.5,
    newMeasureDelay=0.2,
    commandTerminator=b"",
    measureCommand=b"W",
    emptyAnswerValid=False,
)


class ScaleReadHardwareProxy(http.Controller):
    @http.route("/hw_proxy/scale_read", type="jsonrpc", auth="none", cors="*")
    def scale_read(self):
        if ACTIVE_SCALE:
            return {"weight": ACTIVE_SCALE._scale_read_hw_proxy()}
        return None


class ScaleDriver(SerialDriver):

    last_sent_value = None

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)
        self.device_type = "scale"
        self._set_actions()
        self._is_reading = True

        global ACTIVE_SCALE  # noqa: PLW0603 -- Updates process-wide state shared by callers of this module.
        ACTIVE_SCALE = self
        proxy_drivers["scale"] = ACTIVE_SCALE

    def get_status(self):

        status = self._status
        return {"status": status["status"], "messages": [status["message_title"]]}

    def _set_actions(self) -> None:

        self._actions.update(
            {
                "read_once": self._read_once_action,
                "start_reading": self._start_reading_action,
                "stop_reading": self._stop_reading_action,
            }
        )

    def _start_reading_action(self, data) -> None:
        self._is_reading = True

    def _stop_reading_action(self, data) -> None:
        self._is_reading = False

    def _read_once_action(self, data) -> None:

        self._read_weight()
        self.last_sent_value = self.data["result"]

    @staticmethod
    def _get_raw_response(connection):

        answer = []
        while True:
            char = connection.read(1)
            if not char:
                break
            answer.append(bytes(char))
        return b"".join(answer)

    def _read_weight(self) -> None:

        protocol = self._protocol
        self._connection.write(protocol.measureCommand + protocol.commandTerminator)
        answer = self._get_raw_response(self._connection)
        match = re.search(self._protocol.measureRegexp, answer)
        if match:
            self.data = {"result": float(match.group(1)), "status": self._status}
        else:
            self._read_status(answer)

    def _scale_read_hw_proxy(self):
        with self._device_lock:
            self._read_weight()
        return self.data["result"]

    def _take_measure(self):

        with self._device_lock:
            self._read_weight()
            if (
                self.data["result"] != self.last_sent_value
                or self._status["status"] == self.STATUS_ERROR
            ):
                self.last_sent_value = self.data["result"]
                event_manager.device_changed(self)


class Toledo8217Driver(ScaleDriver):

    _protocol = Toledo8217Protocol

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)
        self.device_manufacturer = "Toledo"

    @classmethod
    def supported(cls, device):

        protocol = cls._protocol

        try:
            with serial_connection(
                device["identifier"], protocol, is_probing=True
            ) as connection:
                connection.reset_input_buffer()

                connection.write(b"Ehello" + protocol.commandTerminator)
                time.sleep(protocol.commandDelay)
                answer = connection.read(8)
                if answer == b"\x02E\rhello":
                    connection.write(b"F" + protocol.commandTerminator)
                    connection.reset_input_buffer()
                    return True
        except serial.serialutil.SerialTimeoutException:
            pass
        except Exception:
            _logger.exception(
                "Error while probing %s with protocol %s", device, protocol.name
            )
        return False

    @staticmethod
    def _get_raw_response(connection):
        return connection.read_until(b"\r")

    def _read_status(self, answer):
        status_char_error_bits = (
            "Scale in motion",
            "Over capacity",
            "Under zero",
            "Outside zero capture range",
            "Center of zero",
            "Net weight",
            "Bad Command from host",
        )

        status_match = self._protocol.statusRegexp and re.search(
            self._protocol.statusRegexp, answer
        )
        if status_match:
            status_char = status_match.group(
                1
            ).decode()
            binary_status_char = format(ord(status_char), "08b")
            for index, bit in enumerate(
                binary_status_char[1:][::-1]
            ):
                if int(bit):
                    _logger.debug(
                        "Scale error: %s. Status string: %s. Scale answer: %s.",
                        status_char_error_bits[index],
                        binary_status_char,
                        answer,
                    )
                    self.data = {
                        "result": 0,
                        "status": self._status,
                    }
                    break
