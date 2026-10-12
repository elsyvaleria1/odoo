import hashlib
import io
import itertools
import logging
import pathlib
import pprint
import re
import textwrap
import zipfile

from odoo import http
from odoo.http import Response, Stream, Unauthorized, request
from odoo.libs.json import loads as json_loads
from odoo.modules import get_module_path
from odoo.modules.module import Manifest
from odoo.tools.misc import consteq, str2bool

from odoo.addons.integration.tools.authentication import is_bearer_token_valid

_logger = logging.getLogger(__name__)

_iot_logger = logging.getLogger(__name__ + ".iot_log")
_iot_logger.setLevel(logging.DEBUG)

_logger = logging.getLogger(__name__)


def get_unique_name(name):
    existing_names = (
        request.env["iot.box"]
        .sudo()
        .search([("name", "ilike", name + "%")])
        .mapped("name")
    )
    base_name = name
    suffix = 1
    while name in existing_names:
        name = f"{base_name} ({suffix})"
        suffix += 1

    return name


class IoTBoxLookup:
    def _search_box(self, identifier):
        return (
            request.env["iot.box"]
            .sudo()
            .search([("identifier", "=", identifier)], limit=1)
        )

    def _calling_box(self, identifier):
        box = self._search_box(identifier) if identifier else request.env["iot.box"]
        headers = request.httprequest.headers
        if "Authorization" in headers:
            if not (box and is_bearer_token_valid(dict(headers), box.token)):
                raise Unauthorized
            return box
        if box:
            box._note_unverified_call(request.httprequest.path)
        return box


class IoTController(IoTBoxLookup, http.Controller):
    def _get_handler_modules(self, box):
        installed = set(
            request.env["ir.module.module"]
            .sudo()
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        in_image = {
            manifest.name
            for manifest in Manifest.get_all_addon_manifests()
            if manifest["iot_handlers_in_image"]
        }

        modules = installed | {"iot_drivers"}
        if re.search(r"\d{4}\.\d{2}\.\d{2}", box.version):
            modules -= in_image

        return sorted(modules | {"iot_drivers"})

    @http.route(
        "/iot/get_handlers",
        type="http",
        auth="receiver",
        receiver="iot.box:_receiver_for_handlers",
        receiver_event="iot_handlers",
        receiver_refusal="iot.box:_prepare_box_refusal_response",
        csrf=False,
        typed=True,
    )
    def get_handlers(self, identifier: str, auto: bool):
        box = request.admission.subject
        if auto and not box.drivers_auto_update:
            raise Unauthorized(
                description="Auto update is disabled on the box '%s'." % identifier
            )
        incompatible_filename = "_L.py" if box.version[0] == "W" else "_W.py"
        modules = self._get_handler_modules(box)

        fobj = io.BytesIO()
        with zipfile.ZipFile(fobj, "w", zipfile.ZIP_DEFLATED) as zf:
            for module in modules:
                module_path = get_module_path(module)
                if module_path:
                    iot_handlers = pathlib.Path(module_path) / "iot_handlers"
                    for handler in iot_handlers.glob("*/*"):
                        if handler.name.startswith((".", "_")) or handler.name.endswith(
                            incompatible_filename
                        ):
                            continue
                        zf.write(handler, handler.relative_to(iot_handlers))

        etag = hashlib.sha256(fobj.getvalue()).hexdigest()
        if etag == request.httprequest.headers.get("If-None-Match"):
            return request.prepare_response("", headers=[("ETag", etag)], status=304)

        return Stream(
            type="data",
            data=fobj.getvalue(),
            download_name="iot_handlers.zip",
            etag=etag,
            size=fobj.tell(),
            public=True,
        ).prepare_response()

    @http.route("/iot/keyboard_layouts", type="http", auth="public", csrf=False)
    def load_keyboard_layouts(self, available_layouts):  # noqa: E8528 -- an IoT box seeds the layout table once, before any box is paired
        if not request.env["iot.keyboard.layout"].sudo().search_count([], limit=1):
            request.env["iot.keyboard.layout"].sudo().create(
                json_loads(available_layouts)
            )
        return ""

    @http.route("/iot/box/<string:identifier>/display_url", type="http", auth="public")
    def get_url(self, identifier):
        urls = {}
        iotbox = self._search_box(identifier)
        if iotbox:
            iot_devices = iotbox.device_ids.filtered(
                lambda device: device.type == "display"
            )
            for device in iot_devices:
                urls[device.identifier] = device.display_url
        return request.prepare_json_response(urls)

    @http.route("/iot/box/send_websocket", type="jsonrpc", auth="public")
    def iot_box_send_websocket(
        self, session_id, iot_box_identifier, device_identifier, status, **kwargs
    ):
        box = self._calling_box(iot_box_identifier)
        if not box:
            _logger.warning(
                "No IoT Box found with identifier: '%s'. Request ignored",
                iot_box_identifier,
            )
            return

        if (
            device_identifier
            and not request.env["iot.device"]
            .sudo()
            .search(
                [("identifier", "=", device_identifier), ("iot_id", "=", box.id)],
                limit=1,
            )
            and device_identifier != box.identifier
        ):
            _logger.warning(
                "No IoT device found with identifier '%s' (iot_box_identifier: %s). Request ignored",
                device_identifier,
                iot_box_identifier,
            )
            return

        session_id = session_id or kwargs.get("owner")
        request.env["iot.channel"]._send_reply(
            {
                "session_id": session_id,
                "iot_box_identifier": iot_box_identifier,
                "device_identifier": device_identifier,
                "message": {
                    "status": status,
                    "result": kwargs.get("result", {}),
                    "action_args": kwargs.get("action_args", {}),
                },
            },
            "operation_confirmation",
            box=box,
            unrouted="remote_debug"
            if not session_id and not device_identifier
            else None,
        )

    @http.route("/iot/box/webrtc_answer", type="jsonrpc", auth="public")
    def iot_box_webrtc_answer(self, iot_box_identifier, answer, session_id=None):
        box = self._calling_box(iot_box_identifier)
        if not box:
            _logger.warning(
                "No IoT Box found with identifier: '%s'. Request ignored",
                iot_box_identifier,
            )
            return

        request.env["iot.channel"]._send_reply(
            {
                "session_id": session_id,
                "iot_box_identifier": iot_box_identifier,
                "answer": answer,
            },
            "webrtc_answer",
            box=box,
            unrouted="webrtc_offer",
        )

    @http.route("/iot/setup", type="jsonrpc", auth="public")
    def update_box(self, iot_box, devices):
        box = self._upsert_box(iot_box)
        if not box:
            return None

        _logger.info("IoT %s devices:\n%s", box, pprint.pformat(devices))
        self._upsert_devices(box, devices)
        return request.env["iot.channel"].sudo()._box_channel(box)

    def _upsert_box(self, iot_box):
        iot_identifier = iot_box["identifier"]
        new_iot_ip = iot_box["ip"]
        new_iot_version = iot_box["version"]
        box = self._search_box(iot_identifier) or self._search_box(iot_box.get("mac"))
        create_update_value = {
            "identifier": iot_identifier,
            "ip": new_iot_ip,
            "version": new_iot_version,
        }
        if box:
            offered = iot_box.get("token") or ""
            if not (box.token and consteq(offered, box.token)):  # noqa: E8537 -- device: a device's or a service's credential, presented by a program
                pairing_token = request.env["iot.box"]._get_pairing_token()
                if not (pairing_token and consteq(offered, pairing_token)):  # noqa: E8537 -- device: a device's or a service's credential, presented by a program
                    _logger.warning(
                        "IoT %s offered neither the token it was paired with nor "
                        "one this database handed out in the last 15 minutes",
                        iot_identifier,
                    )
                    return request.env["iot.box"]
                _logger.info("IoT %s paired again", iot_identifier)
                create_update_value["token"] = offered
                request.env["iot.box"]._spend_pairing_token()
            if "token" in create_update_value or (
                box.identifier,
                box.ip,
                box.version,
            ) != (iot_identifier, new_iot_ip, new_iot_version):
                _logger.info(
                    "Updating IoT %s with data: %s",
                    box,
                    {k: v for k, v in create_update_value.items() if k != "token"},
                )
                box.write(create_update_value)
            return box

        iot_token = request.env["iot.box"]._get_pairing_token()
        if not consteq(iot_box.get("token"), iot_token):
            _logger.warning(
                "IoT %s offered no pairing token this database handed out in the "
                "last 15 minutes",
                iot_identifier,
            )
            return request.env["iot.box"]

        name = "IoT Box" if new_iot_version.startswith("L") else "Virtual IoT Box"
        create_update_value["name"] = get_unique_name(name)
        _logger.info("Creating IoT with data: %s", create_update_value)
        box = request.env["iot.box"].sudo().create(create_update_value)
        request.env["iot.box"]._spend_pairing_token()
        return box

    def _find_moved_device(self, known, device_identifier, data_device):
        if (
            data_device["type"] == "fiscal_data_module"
            and "BODO001" in data_device["name"]
        ):
            return known.filtered(
                lambda device: (
                    device.type == "fiscal_data_module"
                    and "BODO001" in (device.name or "")
                )
            )[:1]
        return known.browse()

    def _upsert_devices(self, box, devices):
        Device = request.env["iot.device"].sudo()
        known = Device.search([("iot_id", "=", box.id)])
        by_identifier = {device.identifier: device for device in known}
        previously_connected = known.filtered(
            lambda device: device.connection_state == "connected"
        )
        available_types = {s[0] for s in Device._fields["type"].selection}
        available_connections = {s[0] for s in Device._fields["connection"].selection}

        connected = Device
        for device_identifier, data_device in devices.items():
            if (
                data_device["type"] not in available_types
                or data_device["connection"] not in available_connections
            ):
                continue

            moved = self._find_moved_device(known, device_identifier, data_device)
            if moved:
                moved.write({"identifier": device_identifier})
                connected |= moved
                continue

            device = by_identifier.get(device_identifier, Device)
            if not device:
                device = Device.create(
                    {
                        "iot_id": box.id,
                        "name": data_device["name"],
                        "identifier": device_identifier,
                        "type": data_device["type"],
                        "manufacturer": data_device.get("manufacturer"),
                        "connection": data_device["connection"],
                        "subtype": data_device.get("subtype", ""),
                    }
                )
            elif device.type != data_device.get("type") or (
                device.subtype == "" and device.type == "printer"
            ):
                device.write(
                    {
                        "name": data_device.get("name"),
                        "type": data_device.get("type"),
                        "manufacturer": data_device.get("manufacturer"),
                        "subtype": data_device.get("subtype", ""),
                    }
                )
            connected |= device

        connected.write({"connection_state": "connected"})
        (previously_connected - connected).write({"connection_state": "disconnected"})

    @http.route("/iot/box/update_certificate_status", type="jsonrpc", auth="public")
    def update_certificate_status(self, identifier, ssl_certificate_end_date):
        box = self._calling_box(identifier)
        if not box:
            _logger.warning(
                "No IoT Box found with identifier '%s'. Request ignored", identifier
            )
            return

        box.write({"ssl_certificate_end_date": ssl_certificate_end_date})


class IoTLogController(IoTBoxLookup, http.Controller):
    def _is_iot_log_enabled(self) -> bool:
        return bool(
            str2bool(
                request.env.registry.settings.get(
                    request.env, "iot.should_log_iot_logs", True
                )
            )
        )

    @http.route(
        "/iot/log",
        type="http",
        auth="receiver",
        receiver="iot.box:_receiver_for_logs",
        receiver_event="iot_log",
        receiver_refusal="iot.box:_prepare_box_refusal_response",
        csrf=False,
        typed=True,
    )
    def receive_iot_log(self):
        IOT_LOG_LINE_SEPARATOR = b","

        def log_line_transformation(log_line):
            split = log_line.split(IOT_LOG_LINE_SEPARATOR, 1)
            return {
                "levelno": int(split[0]),
                "line_formatted": split[1].decode("utf-8"),
            }

        def log_current_level(log_level, log_lines):
            _iot_logger.log(
                log_level,
                "%s%s",
                init_log_message,
                textwrap.indent("\n".join(["", *log_lines]), " | "),
            )

        def finish_request():
            return Response(status=200, content_type="text/plain")

        if not self._is_iot_log_enabled():
            return finish_request()

        iot_box = request.admission.subject
        request_data_split = request.admission.extra["log_elements"]
        log_details = map(log_line_transformation, request_data_split)
        init_log_message = "IoT box log '%s' #%d received:" % (iot_box.name, iot_box.id)

        for log_level, log_group in itertools.groupby(
            log_details, key=lambda log: log["levelno"]
        ):
            log_lines = [log_line["line_formatted"] for log_line in log_group]
            log_current_level(log_level, log_lines)

        return finish_request()
