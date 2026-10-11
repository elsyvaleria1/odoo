import logging

import serial

from odoo.addons.iot_drivers.event_manager import event_manager
from odoo.addons.iot_drivers.iot_handlers.drivers.serial_base_driver import (
    SerialDriver,
    SerialProtocol,
    serial_connection,
)

_logger = logging.getLogger(__name__)

""" Protocol used for Swedish blackbox to communicate with RS232"""
SwedishBlackboxProtocol = SerialProtocol(
    name="SWEDISH Retail Innovation Cleancash",
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    stopbits=serial.STOPBITS_ONE,
    parity=serial.PARITY_NONE,
    timeout=1,
    writeTimeout=0.3,
    measureRegexp=None,
    statusRegexp=None,
    commandTerminator=b"",
    commandDelay=0.2,
    measureDelay=0.2,
    newMeasureDelay=0.2,
    measureCommand=b"",
    emptyAnswerValid=False,
)

"""Base Json for Swedish black box Messages.
Most of these constants are provided by Retail Innovation Cleancash and should not be changed.
"""
MainStatus = {
    "0": "OK",
    "1": "Warning condition(s) exists",
    "2": "Protocol error condition(s) exists",
    "3": "Non fatal error condition(s) exists",
    "4": "Fatal Error condition(s) exists",
    "5": "Busy (Not used in CCSP v2 currently).",
}

ErrorCode = {
    "001": "Invalid LRC",
    "002": "Unknown message type",
    "003": "Invalid data/parameter",
    "004": "Invalid sequence",
    "005": "Deprecated (Not used)",
    "006": "CleanCash® Not operational",
    "007": "Invalid POS ID",
    "008": "Internal error",
    "009": "License exceeded (CCSP v2)",
    "010": "Internal storage full (CCSP v2)",
    "011": "Invalid sequence number",
}

SeverityError = {
    "0": "Informational",
    "1": "Warning",
    "2": "Protocol error",
    "3": "Non fatal error",
    "4": "Fatal error",
}

StorageStatus = {
    "0": "OK",
    "1": "High level warning",
    "2": "Transaction memory full",
}


class SwedishBlackBoxDriver(SerialDriver):

    _protocol = SwedishBlackboxProtocol

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)

        self.device_type = "fiscal_data_module"
        self.unit_id = device["unit_id"]
        self.protocol_version = device["protocol_version"]
        self.serial_number = 0
        self._set_actions()

    @classmethod
    def supported(cls, device) -> bool | None:

        try:
            protocol = cls._protocol
            packet = cls._wrap_message("SIQ")
            with serial_connection(device["identifier"], protocol) as connection:
                response = cls._send_to_blackbox(packet, connection, 2)
                if len(response) > 1 and response[3] == "SIR":
                    identity = cls._get_identity(connection)
                    if not identity:
                        return False
                    device["unit_id"] = identity["unit_id"]
                    device["protocol_version"] = identity["protocol_version"]
                    if response[4] != "0":
                        _logger.warning(
                            ("Received error: %s - Severity: %s"),
                            MainStatus.get(response[4]),
                            SeverityError.get(response[5][1:2]),
                        )
                        _logger.warning("Sent request: %s", packet)
                    return True
        except serial.serialutil.SerialTimeoutException:
            pass
        except Exception:
            _logger.exception(
                "Error while probing %s with protocol %s", device, protocol.name
            )

    @classmethod
    def _get_identity(cls, connection):
        try:
            response = cls._request_action("IQ", connection)
            if response[3] == "IR":
                return {
                    "unit_id": response[4],
                    "protocol_version": int(response[5]),
                    "firmware_version": response[6],
                }
            else:
                _logger.error("Sent IQ request error")
                return False
        except Exception:
            _logger.exception("Did not receive a response")

    @staticmethod
    def _lrc(msg):

        lrc = ord(msg[0])

        for i in range(1, len(msg)):
            lrc ^= ord(msg[i])

        return f"{int(lrc):02X}"

    def _check_error(self, request, response) -> bool:
        if len(response) <= 1:
            _logger.error("Error request: %s", request)
            _logger.error("Response received: %s", response)
            self.data["status"] = (
                "Sent request: %s without receiving response.",
                request,
            )
            return False

        if len(response) >= 4 and response[3] == "NAK":
            _logger.error("Received error: %s", ErrorCode.get(response[4]))
            _logger.error("Sent request: %s received NACK.", request)
            self.data["status"] = ErrorCode.get(response[4])
            return False

        return True

    def _register_receipt(self, data) -> None:
        if self.protocol_version >= 2:
            self._register_receipt_v2(data)
        else:
            self._register_receipt_v1(data)
        event_manager.device_changed(self)

    def _register_receipt_v2(self, data) -> None:

        self.serial_number += 1
        message = {"message_type": "RR", "serial_number": str(self.serial_number)}
        message.update(data.get("high_level_message"))
        request = "#".join(list(message.values()))
        response = self._request_action(request, self._connection)
        if not self._check_error(request, response):
            return

        self.data["signature_control"] = response[4]
        self.data["unit_id"] = response[5]
        self.data["storage_status"] = StorageStatus.get(response[7])
        self.data["status"] = "ok"

    def _register_receipt_v1(self, data) -> None:

        response = self._request_action("ST", self._connection)
        if not self._check_error("ST", response):
            return

        message_fields = list(data.get("high_level_message").values())
        request_fields = ["RH", *message_fields[0:3], " ", " ", *message_fields[3:]]
        request = "#".join(request_fields)
        response = self._request_action(request, self._connection)
        if not self._check_error(request, response):
            return

        response = self._request_action("SQ", self._connection)
        if not self._check_error("SQ", response):
            return

        self.data["signature_control"] = response[4]
        self.data["unit_id"] = self.unit_id
        self.data["status"] = "ok"

    @classmethod
    def _request_action(cls, data, connection):

        packet = cls._wrap_message(data)
        return cls._send_to_blackbox(packet, connection)

    @classmethod
    def _send_to_blackbox(cls, packet, connection, retry=1):
        connection.reset_input_buffer()
        connection.reset_output_buffer()

        ACK = ""
        retries = 0
        while ACK != "ACK" and retries < retry:
            connection.write(packet)
            response = connection.readline().decode().split("#")

            try:
                if response[3] != "NAK":
                    ACK = "ACK"
                else:
                    _logger.error("Received error: %s", ErrorCode.get(response[4]))
                    _logger.error("Sent request: %s received NACK.", packet)
            except Exception:
                _logger.exception(
                    "sent request: %s without receiving response.",
                    packet,
                )

            retries += 1

        return response

    def _set_actions(self) -> None:

        self._actions.update(
            {
                "registerReceipt": self._register_receipt,
            }
        )

    @classmethod
    def _wrap_message(cls, high_level_message):

        length = 11 + len(high_level_message)
        length = f"{int(length):03X}"
        message = "#!#" + length + "#" + high_level_message + "#"
        lrc = cls._lrc(message)
        message += lrc + "\r"

        return message.encode("utf-8")
