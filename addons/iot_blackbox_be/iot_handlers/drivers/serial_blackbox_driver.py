import logging
import time

import requests
import serial

from odoo.addons.iot_drivers.iot_handlers.drivers.serial_base_driver import (
    SerialDriver,
    SerialProtocol,
    serial_connection,
)
from odoo.addons.iot_drivers.tools import helpers

_logger = logging.getLogger(__name__)

BlackboxProtocol = SerialProtocol(
    name="Blackbox",
    baudrate=19200,
    bytesize=serial.EIGHTBITS,
    stopbits=serial.STOPBITS_ONE,
    parity=serial.PARITY_NONE,
    timeout=1.4,
    writeTimeout=0.2,
    measureRegexp=None,
    statusRegexp=None,
    commandTerminator=b"",
    commandDelay=0.2,
    measureDelay=0.2,
    newMeasureDelay=0.2,
    measureCommand=b"",
    emptyAnswerValid=False,
)

STX = b"\x02"
ETX = b"\x03"
ACK = b"\x06"
NACK = b"\x15"

errors = {
    "000": "No error",
    "001": "PIN accepted.",
    "101": "Fiscal Data Module memory 90% full.",
    "102": "Already handled request.",
    "103": "No record.",
    "199": "Unspecified warning.",
    "201": "No Vat Signing Card or Vat Signing Card broken.",
    "202": "Please initialize the Vat Signing Card with PIN.",
    "203": "Vat Signing Card blocked.",
    "204": "Invalid PIN.",
    "205": "Fiscal Data Module memory full.",
    "206": "Unknown identifier.",
    "207": "Invalid data in message.",
    "208": "Fiscal Data Module not operational.",
    "209": "Fiscal Data Module real time clock corrupt.",
    "210": "Vat Signing Card not compatible with Fiscal Data Module.",
    "299": "Unspecified error.",
    "300": "Fiscal Data Module responded with invalid response. Check cable and power supply. Restart if necessary.",
    "301": "Fiscal Data Module did not respond. Check cable and power supply. Restart if necessary.",
}


class BlackBoxDriver(SerialDriver):
    _protocol = BlackboxProtocol
    priority = 1

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)
        self.device_type = "fiscal_data_module"
        self.sequence_number = 0
        self._set_actions()
        self._certified_ref()

    def _set_actions(self) -> None:

        self._actions.update(
            {
                "batchAction": self._batch_action,
                "registerReceiptWeb": self._request_registerReceiptWeb,
                "registerReceipt": self._request_registerReceipt,
                "registerPIN": self._request_registerPIN,
                "status": self._request_status,
            }
        )

    @classmethod
    def supported(cls, device):
        for i in range(3):
            try:
                protocol = cls._protocol
                probe_message = cls._wrap_low_level_message_around("S00" + str(i))
                with serial_connection(device["identifier"], protocol) as connection:
                    connection.reset_output_buffer()
                    connection.reset_input_buffer()
                    connection.write(probe_message)
                    buffer = connection.read_until(ETX)
                    _logger.info(
                        'Probing %s as a blackbox. Expecting "%s" in response. Device response: "%s"',
                        device,
                        ACK,
                        buffer,
                    )
                    connection.write(ACK)
                    connection.reset_input_buffer()
                    if len(buffer) > 0 and buffer[0:1] == ACK:
                        return True
            except serial.SerialException:
                _logger.exception(
                    "Error while probing %s with protocol %s", device, protocol.name
                )
            time.sleep(3)
        return False

    def _request_status(self, data) -> None:
        blackbox_response = self._send_to_blackbox("S", data, self._connection)
        if blackbox_response:
            self.data["result"] = self._parse_blackbox_response(blackbox_response)

    @classmethod
    def _wrap_low_level_message_around(cls, high_level_message):

        bcc = cls._lrc(high_level_message)
        high_level_message_bytes = (ord(b) for b in high_level_message)

        low_level_message = bytearray()
        low_level_message.append(0x02)
        low_level_message.extend(high_level_message_bytes)
        low_level_message.append(0x03)
        low_level_message.append(bcc)

        return low_level_message

    @staticmethod
    def _lrc(msg):
        lrc = 0
        for character in msg:
            byte = ord(character)
            lrc = (lrc + byte) & 0xFF

        return ((lrc ^ 0xFF) + 1) & 0xFF

    def _box_id(self):
        return "BODO001" + helpers.get_identifier().upper()[-7:]

    def _certified_ref(self) -> None:
        self.data["value"] = self._box_id()

    def _parse_blackbox_response(self, response) -> dict:
        error_code = response[4:10]
        error_message = errors.get(error_code[:3])

        return {
            "identifier": response[0:1],
            "sequence_number": response[1:3],
            "retry_counter": response[3:4],
            "error": {"errorCode": error_code, "errorMessage": error_message},
            "fdm_number": response[10:21],
            "vsc": response[21:35],
            "date": response[35:43],
            "time": response[43:49],
            "type": response[49:51],
            "ticket_counter": response[51:60],
            "total_ticket_counter": response[60:69],
            "signature": response[69:109],
        }

    def send_blackbox_response(self, data, retry_nbr=0) -> None:
        server_url = helpers.get_odoo_server_url() + "/pos_self_blackbox/confirmation"
        try:
            response = requests.post(server_url, json=data, timeout=5)  # noqa: E8518 -- runs on the IoT box, which has no database and so no ir.egress
            response.raise_for_status()
        except requests.Timeout:
            if retry_nbr < 3:
                self.send_blackbox_response(data, retry_nbr + 1)
            else:
                _logger.exception(
                    "Could not reach confirmation status URL: %s", server_url
                )
        except requests.exceptions.RequestException:
            _logger.exception("Could not reach confirmation status URL: %s", server_url)

    def _batch_action(self, batch) -> None:
        responses = []
        for data, action in batch["high_level_message"]:
            if action == "registerReceipt":
                self._registerReceipt(data)
            elif action == "registerPIN":
                self._registerPIN(data)
            else:
                _logger.error("Unknown action '%s' in batch", action)
                continue
            responses.append(self.data["result"])
            if self._is_last_response_error():
                break

        self.data["result"] = responses

    def _is_last_response_error(self) -> bool:
        return (
            "error" in self.data["result"]
            and self.data["result"]["error"]["errorCode"][:3] != "000"
        )

    def _request_registerReceiptWeb(self, data) -> None:
        self._registerReceipt(data["high_level_message"])

        self.send_blackbox_response(
            {
                "order_id": data["id"],
                "device_identifier": self.device_identifier,
                "blackbox_response": self.data["result"],
                "iot_mac": helpers.get_identifier(),
            }
        )

    def _registerReceipt(self, data) -> None:
        if data.get("clock"):
            blackbox_response = self._send_to_blackbox("I", data, self._connection)

        blackbox_response = self._send_to_blackbox("H", data, self._connection)
        if blackbox_response:
            self.data["result"] = self._parse_blackbox_response(blackbox_response)

    def _request_registerReceipt(self, data) -> None:
        self._registerReceipt(data["high_level_message"])

    def _registerPIN(self, data) -> None:
        blackbox_response = self._send_to_blackbox("P", data, self._connection)
        if blackbox_response:
            self.data["result"] = self._parse_blackbox_response(blackbox_response)

    def _request_registerPIN(self, data) -> None:
        self._registerPIN(data["high_level_message"])

    def _send_to_blackbox(
        self, request_type: str, data: dict, connection: serial.Serial
    ) -> str | None:
        error_code = "301"
        for retry in range(3):
            if retry > 0:
                _logger.warning("Retrying (count=%s)...", retry)

            packet = self._wrap_low_level_message_around(
                self._wrap_high_level_message_around(request_type, data, retry)
            )
            connection.reset_output_buffer()
            connection.reset_input_buffer()
            try:
                connection.write(packet)
                buffer = connection.read_until(ETX)

                if not len(buffer) or buffer[0:1] not in (ACK, NACK):
                    _logger.error(
                        "Blackbox did not respond, check the cable connection and the power supply."
                    )
                    error_code = "301"
                    continue

                error_code = "301"
                if buffer[0:1] == NACK:
                    _logger.error("received NACK from blackbox.")
                    continue
                if buffer[0:1] == ACK:
                    buffer = buffer[1:]
                    for _ in range(3):
                        response_data = buffer[1:-1]
                        if (
                            len(buffer)
                            and buffer[0:1] == STX
                            and buffer[-1:] == ETX
                            and self._lrc(response_data.decode())
                            == ord(connection.read(1))
                        ):
                            connection.write(ACK)
                            return response_data.decode()

                        _logger.error(
                            "received ACK but not a valid response, sending NACK... (response: %s)",
                            buffer,
                        )
                        connection.reset_input_buffer()
                        connection.write(NACK)
                        buffer = connection.read_until(ETX)
                    break
            except serial.SerialException:
                _logger.warning(
                    "Error while sending to blackbox with protocol %s",
                    self._protocol.name,
                )
                error_code = "300"
        self.data["result"] = {
            "error": {
                "errorCode": error_code,
                "errorMessage": errors[error_code],
            }
        }
        return None

    def _wrap_high_level_message_around(self, request_type, data, retry=0):
        self.sequence_number += 1
        wrap = request_type + str(self.sequence_number % 100).zfill(2) + str(retry)

        if request_type in ("I", "S"):
            return wrap

        if request_type == "P":
            return wrap + data

        wrap += "{:>8}".format(data["date"])
        wrap += "{:>6}".format(data["ticket_time"])
        wrap += "{:>11}".format(data["insz_or_bis_number"])
        wrap += self._box_id()
        wrap += "{:>6}".format(data["ticket_number"])[-6:]
        wrap += "{:>2}".format(data["type"])
        wrap += "{:>11}".format(data["receipt_total"].zfill(3))[-11:]
        wrap += "2100" + "{:>11}".format(data["vat1"].zfill(3))[-11:]
        wrap += "1200" + "{:>11}".format(data["vat2"].zfill(3))[-11:]
        wrap += " 600" + "{:>11}".format(data["vat3"].zfill(3))[-11:]
        wrap += " 000" + "{:>11}".format(data["vat4"].zfill(3))[-11:]
        wrap += "{:>40}".format(data["plu"])

        return wrap

    def _set_name(self):

        try:
            name = "%s serial %s - %s" % (
                self._protocol.name,
                self.device_type,
                self._box_id(),
            )
        except Exception:
            name = "Unknown Serial Device"
        self.device_name = name

    def run(self):
        with serial_connection(self.device_identifier, self._protocol) as connection:
            self._connection = connection
            self.data["status"] = self.STATUS_CONNECTED
            while not self._stopped.is_set():
                time.sleep(self._protocol.newMeasureDelay)

            self.data["status"] = self.STATUS_DISCONNECTED
