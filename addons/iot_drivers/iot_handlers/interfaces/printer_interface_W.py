import logging
from threading import Lock

import win32print

from odoo.addons.iot_drivers.interface import Interface

_logger = logging.getLogger(__name__)

win32print_lock = Lock()


class PrinterInterface(Interface):
    _loop_delay = 30
    connection_type = "printer"

    def get_devices(self):
        printer_devices = {}
        with win32print_lock:
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)

            for printer in printers:
                identifier = printer[2]
                handle_printer = win32print.OpenPrinter(identifier)
                printer_details = win32print.GetPrinter(handle_printer, 2)
                printer_port = None
                if printer_details:
                    printer_port = printer_details.get("pPortName")
                if printer_port is None:
                    _logger.warning(
                        'Printer "%s" has no port name. Used dummy port', identifier
                    )
                    printer_port = "IOT_DUMMY_PORT"

                if printer_port == "PORTPROMPT:":
                    continue

                printer_devices[identifier] = {
                    "identifier": identifier,
                    "printer_handle": handle_printer,
                    "port": printer_port,
                }
        return printer_devices
