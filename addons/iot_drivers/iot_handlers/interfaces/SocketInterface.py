import contextlib
import logging
import socket

from odoo.addons.iot_drivers.interface import Interface
from odoo.addons.iot_drivers.main import iot_devices

_logger = logging.getLogger(__name__)


socket_devices = {}


class SocketInterface(Interface):
    connection_type = "socket"

    def __init__(self) -> None:
        super().__init__()
        self.open_socket(9000)

    def open_socket(self, port) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen()

    @staticmethod
    def create_socket_device(dev, addr) -> None:
        _logger.debug("Creating new socket_device")
        socket_devices[addr] = type("", (), {"dev": dev})

    def replace_socket_device(self, dev, addr) -> None:
        driver_thread = iot_devices.get(addr)

        old_dev = socket_devices[addr].dev
        _logger.debug("Closing socket: %s", old_dev)
        with contextlib.suppress(OSError):
            old_dev.shutdown(socket.SHUT_RD)
        old_dev.close()

        if driver_thread:
            _logger.debug("Waiting for driver thread to finish")
            driver_thread.join()
            _logger.debug("Driver thread finished")

        del socket_devices[addr]

        _logger.debug("Updating _detected_devices")
        new_detected_devices = dict.fromkeys(self._detected_devices, 0)
        if addr in new_detected_devices:
            del new_detected_devices[addr]
            _logger.debug("Updated _detected_devices")
        else:
            _logger.warning(
                "socket_device entry %s was not found in _detected_devices", addr
            )
        self._detected_devices = new_detected_devices

        SocketInterface.create_socket_device(dev, addr)

    def get_devices(self):
        try:
            dev, addr = self.sock.accept()
            _logger.debug("Accepted new socket connection: %s", addr)
            if not addr:
                _logger.warning("Socket accept returned no address")
                return socket_devices

            if addr[0] not in socket_devices:
                self.create_socket_device(dev, addr[0])
            else:
                self.replace_socket_device(dev, addr[0])
        except OSError:
            pass

        return socket_devices.copy()
