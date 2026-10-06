import base64
import json
import logging
from datetime import UTC, datetime

import defusedxml.ElementTree as ET

from odoo import fields, http
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from ..tools import find_element, find_text
from odoo.addons.integration.tools.admission import Refused

_logger = logging.getLogger(__name__)


def _safe_int(value, default=0):
    try:
        if isinstance(value, str) and value.startswith("0x"):
            return int(value, 16)
        return int(value)
    except ValueError, TypeError:
        return default


_RECEIVER = "device.device:_receiver_for_access_device"


class AccessDeviceController(http.Controller):
    @http.route(
        "/access_device/webhook/<string:identifier>",
        type="http",
        auth="receiver",
        receiver=_RECEIVER,
        receiver_event="access_event",
        receiver_refusal="device.device:_prepare_access_device_refusal_response",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the reader
        save_session=False,
        typed=True,
    )
    def webhook(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        try:
            content_type = request.httprequest.content_type or ""
            _logger.info("Access device webhook hit: content_type=%s", content_type)

            if "multipart" in content_type:
                self._process_multipart(device)
            else:
                body = admission.body.decode("utf-8", errors="replace")
                if body:
                    self._process_event(device, body, content_type)
            admission.settle()
        except Exception as error:
            _logger.exception("Access device webhook error")
            admission.settle(f"{type(error).__name__}: {error}")
        return request.prepare_response("OK", status=200)

    @http.route(
        "/access_device/commands/<string:identifier>",
        type="http",
        auth="receiver",
        receiver=_RECEIVER,
        receiver_event="command_poll",
        methods=["GET"],
        save_session=False,
        typed=True,
    )
    def poll_commands(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        try:
            commands = (
                request.env["access.command"]
                .sudo()
                .search(
                    [
                        ("device_id", "=", device.id),
                        ("state", "=", "pending"),
                    ],
                    order="create_date asc",
                    limit=10,
                )
            )

            result = []
            for cmd in commands:
                result.append(
                    {
                        "id": cmd.id,
                        "type": cmd.command_type,
                        "payload": json_loads(cmd.payload) if cmd.payload else {},
                    }
                )
                cmd.write(
                    {
                        "state": "sent",
                        "sent_date": fields.Datetime.now(),
                    }
                )

            if result:
                # A poll leaves no row; a delivery does.
                admission.retag("command_delivery")
                admission.keep()
                admission.annotate(processing_result=f"{len(result)} command(s)")
            admission.settle()
            return request.prepare_json_response({"commands": result})

        except Exception as error:
            _logger.exception("Access device command poll error")
            admission.annotate(status_code=500)
            admission.settle(f"{type(error).__name__}: {error}")
            return request.prepare_json_response(
                {"error": "internal_error"}, status=500
            )

    @http.route(
        "/access_device/result/<string:identifier>",
        type="http",
        auth="receiver",
        receiver=_RECEIVER,
        receiver_event="command_result",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the reader
        save_session=False,
        typed=True,
    )
    def command_result(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        try:
            if not admission.body:
                admission.refuse(400, "the request body is empty", "empty_body")
            data = admission.json()
            cmd_id = data.get("command_id")
            if not cmd_id:
                return request.prepare_json_response(
                    {"error": "missing_command_id"}, status=400
                )

            command = request.env["access.command"].sudo().browse(cmd_id)
            if not command.exists() or command.device_id.id != device.id:
                return request.prepare_json_response(
                    {"error": "command_not_found"}, status=404
                )

            vals = {"execute_date": fields.Datetime.now()}
            if data.get("success"):
                vals["state"] = "executed"
                vals["result"] = json_dumps(data.get("result", {}))
            else:
                vals["state"] = "error"
                vals["error_message"] = data.get("error", "Unknown error")

            command.write(vals)
            admission.settle()
            return request.prepare_json_response({"status": "ok"})

        except Refused:
            raise
        except Exception as error:
            _logger.exception("Access device command result error")
            admission.settle(f"{type(error).__name__}: {error}")
            return request.prepare_json_response(
                {"error": "internal_error"}, status=500
            )

    @http.route(
        "/access_device/heartbeat/<string:identifier>",
        type="http",
        auth="receiver",
        receiver=_RECEIVER,
        receiver_event="access_heartbeat",
        receiver_refusal="device.device:_prepare_access_device_refusal_response",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the reader
        save_session=False,
        typed=True,
    )
    def heartbeat(self, identifier: str, **kwargs):
        try:
            request.admission.subject._touch_last_seen()
        except Exception:
            _logger.exception("Access device heartbeat error")
        return request.prepare_response("OK", status=200)

    def _process_event(self, device, body, content_type):
        if "json" in content_type or body.lstrip().startswith("{"):
            try:
                data = json_loads(body)
                self._process_json_event(device, data, raw=body)
                return
            except json.JSONDecodeError:
                pass

        if "xml" in content_type or body.lstrip().startswith("<"):
            self._process_xml_event(device, body)
            return

        _logger.warning("AccessDevice: Unknown content format: %s", content_type)

    def _process_json_event(self, device, data, raw="", image=None):
        event_type_raw = data.get("eventType", "")

        if event_type_raw != "AccessControllerEvent":
            _logger.debug("AccessDevice: Non-access JSON event: %s", event_type_raw)
            return

        ace = data.get("AccessControllerEvent", {})
        major = _safe_int(ace.get("majorEventType", 0))
        sub = _safe_int(ace.get("subEventType", 0))
        employee_no = str(ace.get("employeeNoString", "")).strip()
        card_no = str(ace.get("cardNo", "")).strip()
        person_name = str(ace.get("name", "")).strip()
        serial_no = str(ace.get("serialNo", "")).strip()
        attendance = str(ace.get("attendanceStatus", "")).strip()
        event_time_str = data.get("dateTime", "")

        self._create_access_event(
            device,
            major,
            sub,
            employee_no,
            card_no,
            person_name,
            serial_no,
            attendance,
            event_time_str,
            event_data=raw or json_dumps(data),
            image=image,
        )

    def _process_multipart(self, device):
        text_data = None
        image_data = None
        content_type_text = ""

        raw_data = request.httprequest.get_data()
        boundary = None

        ct = request.httprequest.content_type or ""
        if "boundary=" in ct:
            boundary = ct.split("boundary=")[-1].strip()

        if boundary and raw_data:
            parts = raw_data.split(f"--{boundary}".encode())
            for part in parts:
                if not part or part in {b"--", b"--\r\n"}:
                    continue
                if b"\r\n\r\n" in part:
                    header_section, body = part.split(b"\r\n\r\n", 1)
                    headers_str = header_section.decode("utf-8", errors="replace")

                    if (
                        "image" in headers_str.lower()
                        or "jpeg" in headers_str.lower()
                        or "jpg" in headers_str.lower()
                    ):
                        image_data = base64.b64encode(body.rstrip(b"\r\n"))
                    elif "json" in headers_str.lower():
                        text_data = body.decode("utf-8", errors="replace").strip()
                        content_type_text = "json"
                    elif "xml" in headers_str.lower():
                        text_data = body.decode("utf-8", errors="replace").strip()
                        content_type_text = "xml"
                    elif not text_data:
                        text_data = body.decode("utf-8", errors="replace").strip()

        if not image_data:
            for file_storage in request.httprequest.files.values():
                if file_storage.content_type and "image" in file_storage.content_type:
                    image_data = base64.b64encode(file_storage.read())

        if text_data:
            if content_type_text == "json" or text_data.lstrip().startswith("{"):
                try:
                    data = json_loads(text_data)
                    self._process_json_event(
                        device, data, raw=text_data, image=image_data
                    )
                    return
                except json.JSONDecodeError:
                    pass
            self._process_xml_event(device, text_data, image=image_data)

    def _process_xml_event(self, device, xml_string, image=None):
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as e:
            _logger.warning("AccessDevice: Failed to parse XML: %s", e)
            return

        event_type_raw = find_text(root, "eventType")

        if event_type_raw != "AccessControllerEvent":
            _logger.debug("AccessDevice: Non-access XML event: %s", event_type_raw)
            return

        ace = find_element(root, "AccessControllerEvent")
        if ace is None:
            _logger.warning("AccessDevice: No AccessControllerEvent element found")
            return

        major = _safe_int(find_text(ace, "majorEventType"))
        sub = _safe_int(find_text(ace, "subEventType"))
        employee_no = find_text(ace, "employeeNoString")
        card_no = find_text(ace, "cardNo")
        person_name = find_text(ace, "name")
        serial_no = find_text(ace, "serialNo")
        attendance = find_text(ace, "attendanceStatus")
        event_time_str = find_text(root, "dateTime")

        self._create_access_event(
            device,
            major,
            sub,
            employee_no,
            card_no,
            person_name,
            serial_no,
            attendance,
            event_time_str,
            event_data=xml_string,
            image=image,
        )

    def _create_access_event(
        self,
        device,
        major,
        sub,
        employee_no,
        card_no,
        person_name,
        serial_no,
        attendance,
        event_time_str,
        event_data="",
        image=None,
    ):
        mapped_type = request.env["access.event"].sudo().map_event_type(major, sub)
        event_uid = serial_no or None

        if event_uid:
            existing = (
                request.env["access.event"]
                .sudo()
                .search(
                    [
                        ("device_id", "=", device.id),
                        ("event_uid", "=", event_uid),
                    ],
                    limit=1,
                )
            )
            if existing:
                _logger.debug("AccessDevice: Duplicate event %s, skipping", event_uid)
                return

        employee = False
        if employee_no:
            employee = (
                request.env["hr.employee"]
                .sudo()
                .search([("barcode", "=", employee_no)], limit=1)
            )

        event_time = self._parse_event_time(event_time_str)

        vals = {
            "device_id": device.id,
            "event_type": mapped_type,
            "event_time": event_time,
            "event_data": event_data,
            "major_type": major,
            "sub_type": sub,
            "employee_no": employee_no or False,
            "card_no": card_no or False,
            "person_name": person_name or False,
            "event_uid": event_uid,
            "attendance_status": attendance or False,
        }
        if employee:
            vals["employee_id"] = employee.id
        if image:
            vals["image"] = image

        request.env["access.event"].sudo().create(vals)
        _logger.info(
            "Access event: device=%s type=%s major=%s sub=%s employee=%s",
            device.name,
            mapped_type,
            major,
            sub,
            employee_no or "unknown",
        )

    @staticmethod
    def _parse_event_time(event_time_str):
        if not event_time_str:
            return fields.Datetime.now()
        try:
            parsed = datetime.fromisoformat(event_time_str.strip())
        except ValueError, TypeError:
            _logger.debug(
                "AccessDevice: Could not parse event time: %s", event_time_str
            )
            return fields.Datetime.now()
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
