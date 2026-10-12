import io
import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from base64 import b64decode

import escpos.exceptions
import escpos.printer
from escpos.escpos import EscposIO
from PIL import Image, ImageOps

from odoo.addons.iot_drivers.driver import Driver
from odoo.addons.iot_drivers.event_manager import event_manager
from odoo.addons.iot_drivers.main import iot_devices

_logger = logging.getLogger(__name__)


def _read_escpos_with_retry(self):
    assert self.device

    for attempt in range(5):
        if result := self.device.read(self.in_ep, 16):
            return result

        time.sleep(0.05)
        _logger.debug("Read attempt %s failed", attempt)
    return b""


escpos.printer.Usb._read = _read_escpos_with_retry


class EscposNotAvailableError(RuntimeError):
    pass


class PrinterDriverBase(Driver, ABC):
    connection_type = "printer"
    job_timeout_seconds = 30

    RECEIPT_PRINTER_COMMANDS = {
        "star": {
            "center": b"\x1b\x1d\x61\x01",
            "cut": b"\x1b\x64\x02",
            "title": b"\x1b\x69\x01\x01%s\x1b\x69\x00\x00",
            "drawers": [b"\x07", b"\x1a"],
        },
        "escpos": {
            "center": b"\x1b\x61\x01",
            "cut": b"\x1d\x56\x41\n",
            "title": b"\x1b\x21\x30%s\x1b\x21\x00",
            "drawers": [
                b"\x1b\x3d\x01",
                b"\x1b\x70\x00\x19\x19",
                b"\x1b\x70\x01\x19\x19",
            ],
        },
    }

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)

        self.device_type = "printer"
        self.job_ids = []
        self.job_action_ids = {}
        self.escpos_device = None
        self.escpos_lock = threading.Lock()

        self._actions.update(
            {
                "cashbox": self.open_cashbox,
                "print_receipt": self.print_receipt,
                "status": self.print_status,
                "": self._action_default,
            }
        )

    @classmethod
    def get_status(cls):
        status = (
            "connected"
            if any(
                iot_devices[d].device_type == "printer"
                and iot_devices[d].device_connection == "direct"
                for d in iot_devices
            )
            else "disconnected"
        )
        return {"status": status, "messages": ""}

    def send_status(self, status, message=None, action_unique_id=None) -> None:
        if status == "error":
            self._recent_action_ids.pop(action_unique_id, None)
        self.data["status"] = status
        self.data["message"] = message
        event_manager.device_changed(self, {"session_id": self.data.get("owner")})

    def print_receipt(self, data) -> None:
        _logger.debug("print_receipt called for printer %s", self.device_name)

        receipt = b64decode(data["receipt"])
        im = Image.open(io.BytesIO(receipt))

        im = im.convert("L")
        im = ImageOps.invert(im)
        im = im.convert("1")

        print_command = getattr(self, "format_%s" % self.receipt_protocol)(im)
        self.print_raw(print_command, action_unique_id=data.get("action_unique_id"))

    @classmethod
    def format_escpos_bit_image_raster(cls, im):
        width = int((im.width + 7) / 8)

        raster_send = b"\x1d\x76\x30\x00"
        max_slice_height = 255

        raster_data = b""
        dots = im.tobytes()
        while len(dots):
            im_slice = dots[: width * max_slice_height]
            slice_height = int(len(im_slice) / width)
            raster_data += (
                raster_send
                + width.to_bytes(2, "little")
                + slice_height.to_bytes(2, "little")
                + im_slice
            )
            dots = dots[width * max_slice_height :]

        return raster_data + cls.RECEIPT_PRINTER_COMMANDS["escpos"]["cut"]

    @classmethod
    def extract_columns_from_picture(cls, im, line_height):
        width_pixels, height_pixels = im.size
        for left in range(0, width_pixels, line_height):
            box = (left, 0, left + line_height, height_pixels)
            im_chunk = im.transform((line_height, height_pixels), Image.EXTENT, box)
            yield im_chunk.tobytes()

    def format_escpos_bit_image_column(
        self,
        im,
        high_density_vertical=True,
        high_density_horizontal=True,
        size_scale=100,
    ):
        size_scale_ratio = size_scale / 100
        size_scale_width = int(im.width * size_scale_ratio)
        size_scale_height = int(im.height * size_scale_ratio)
        im = im.resize((size_scale_width, size_scale_height))
        im = im.transpose(Image.ROTATE_270).transpose(Image.FLIP_LEFT_RIGHT)

        ESC = b"\x1b"
        density_byte = (1 if high_density_horizontal else 0) + (
            32 if high_density_vertical else 0
        )
        nL = im.height & 0xFF
        nH = (im.height >> 8) & 0xFF
        HEADER = ESC + b"*" + bytes([density_byte, nL, nH])

        raster_data = ESC + b"3\x10"
        line_height = 24 if high_density_vertical else 8
        for column in self.extract_columns_from_picture(im, line_height):
            raster_data += HEADER + column + b"\n"
        raster_data += ESC + b"2"
        return raster_data + self.RECEIPT_PRINTER_COMMANDS["escpos"]["cut"]

    def format_escpos(self, im):

        image_mode = "raster"

        options_str = self.device_name.split("__")
        option_str = ""
        if len(options_str) > 2:
            option_str = options_str[1].upper()
            if option_str.startswith("IMC"):
                image_mode = "column"

        if image_mode == "raster":
            return self.format_escpos_bit_image_raster(im)

        high_density_vertical = True
        high_density_horizontal = True
        scale = 100

        options = option_str.split("_")
        for option in options:
            if option == "LDV":
                high_density_vertical = False
            elif option == "LDH":
                high_density_horizontal = False
            elif option.startswith("SCALE"):
                scale_value_str = re.search(r"\d+$", option)
                if scale_value_str is not None:
                    scale = int(scale_value_str.group())
                else:
                    raise ValueError(
                        "Missing printer SCALE parameter integer value in option: "
                        + option
                    )

        return self.format_escpos_bit_image_column(
            im, high_density_vertical, high_density_horizontal, scale
        )

    def open_cashbox(self, data) -> None:
        _logger.debug("open_cashbox called for printer %s", self.device_name)

        commands = self.RECEIPT_PRINTER_COMMANDS[self.receipt_protocol]
        for drawer in commands["drawers"]:
            self.print_raw(drawer, action_unique_id=data.get("action_unique_id"))

    def _check_status_escpos(self, escpos_device, action_unique_id) -> bool:
        if not escpos_device.is_online():
            _logger.warning("Printer %s is not ready, aborting print", self.device_name)
            self.send_status(
                status="error",
                message="ERROR_OFFLINE",
                action_unique_id=action_unique_id,
            )
            return False
        paper_status = escpos_device.paper_status()
        if paper_status == 0:
            _logger.warning("Printer %s has no paper, aborting print", self.device_name)
            self.send_status(
                status="error",
                message="ERROR_NO_PAPER",
                action_unique_id=action_unique_id,
            )
            return False
        elif paper_status == 1:
            self.send_status(status="warning", message="WARNING_LOW_PAPER")
        return True

    def print_raw_escpos(self, data, action_unique_id=None) -> bool:
        if not self.escpos_device:
            raise EscposNotAvailableError
        try:
            with self.escpos_lock, EscposIO(self.escpos_device, autocut=False) as esc:
                esc.printer.open()
                if not self._check_status_escpos(esc.printer, action_unique_id):
                    return False
                esc.printer._raw(data)
            self.send_status(status="success")
            return True
        except escpos.exceptions.Error, OSError, AssertionError, TypeError:
            self.escpos_device = None
            raise EscposNotAvailableError from None

    def run(self):
        while True:
            for job_id in self.job_ids:
                self._check_job_status(job_id)
            time.sleep(1)

    @abstractmethod
    def print_raw(self, data, action_unique_id=None):
        pass

    @abstractmethod
    def print_status(self, data):
        pass

    @abstractmethod
    def _action_default(self, data):
        pass

    @abstractmethod
    def _check_job_status(self, job_id):
        pass
