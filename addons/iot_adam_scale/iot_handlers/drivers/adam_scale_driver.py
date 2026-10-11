import logging
import time

import serial

from odoo.addons.iot_drivers.event_manager import event_manager
from odoo.addons.iot_drivers.iot_handlers.drivers.serial_base_driver import (
    SerialProtocol,
    serial_connection,
)
from odoo.addons.iot_drivers.iot_handlers.drivers.serial_scale_driver import ScaleDriver

_logger = logging.getLogger(__name__)


ADAMEquipmentProtocol = SerialProtocol(
    name="Adam Equipment",
    baudrate=4800,
    bytesize=serial.EIGHTBITS,
    stopbits=serial.STOPBITS_ONE,
    parity=serial.PARITY_NONE,
    timeout=0.2,
    writeTimeout=0.2,
    measureRegexp=rb"\s*([0-9.]+)kg",
    statusRegexp=None,
    commandTerminator=b"\r\n",
    commandDelay=0.2,
    measureDelay=0.5,
    newMeasureDelay=5,
    measureCommand=b"P",
    emptyAnswerValid=True,
)


class AdamEquipmentDriver(ScaleDriver):
    """Driver for the Adam Equipment serial scale."""

    _protocol = ADAMEquipmentProtocol
    priority = (
        -1
    )

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)
        self._is_reading = False
        self._last_weight_time = 0
        self.device_manufacturer = "Adam"

    def _check_last_weight_time(self) -> None:

        TIME_WEIGHT_KEPT = 10

        if self.data["value"] is None:
            if time.time() - self._last_weight_time > TIME_WEIGHT_KEPT:
                self.data["value"] = 0
        else:
            self._last_weight_time = time.time()

    def _take_measure(self):

        if self._is_reading:
            with self._device_lock:
                self._read_weight()
                self._check_last_weight_time()
                if (
                    self.data["value"] != self.last_sent_value
                    or self._status["status"] == self.STATUS_ERROR
                ):
                    self.last_sent_value = self.data["value"]
                    event_manager.device_changed(self)
        else:
            time.sleep(0.5)

    def _scale_read_hw_proxy(self):

        time.sleep(3)
        with self._device_lock:
            self._read_weight()
            self._check_last_weight_time()
        return self.data["value"]

    @classmethod
    def supported(cls, device):

        protocol = cls._protocol

        try:
            with serial_connection(
                device["identifier"], protocol, is_probing=True
            ) as connection:
                connection.write(protocol.measureCommand + protocol.commandTerminator)
                return True
        except serial.serialutil.SerialTimeoutException:
            pass
        except Exception:
            _logger.exception(
                "Error while probing %s with protocol %s", device, protocol.name
            )
        return False

    def _read_status(self, answer):
        pass
