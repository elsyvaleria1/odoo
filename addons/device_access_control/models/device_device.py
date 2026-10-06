import base64
import json
import logging
from typing import NamedTuple
from xml.sax.saxutils import escape as xml_escape

import defusedxml.ElementTree as ET

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from ..tools import find_text
from odoo.addons.integration.tools import (
    CommError,
    CommTimeoutError,
)


class ISAPIResponse(NamedTuple):
    content: bytes
    headers: dict[str, str]


_logger = logging.getLogger(__name__)


def isapi_content_type(content: bytes) -> str:
    stripped = content.lstrip()
    if stripped[:2] == b"--":
        boundary = stripped.split(b"\r\n", 1)[0].lstrip(b"-").decode("ascii", "replace")
        return f"multipart/form-data; boundary={boundary}"
    if stripped[:1] == b"<":
        return "application/xml"
    if stripped[:1] in (b"{", b"["):
        return "application/json"
    if stripped[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "application/octet-stream"


ACCESS_CATEGORY_CODE = "access_control"
AUTH_MODE_PARAM = "device_access_control.auth_mode"
# A reader posts a face capture beside its event; the log keeps a head of
# the body, never the picture.
ACCESS_MAX_PAYLOAD = 8 * 1024 * 1024
ACCESS_MAX_LOGGED_PAYLOAD = 65536
EHOME_BRIDGE_DEFAULT_URL = "http://localhost:8085"
EHOME_DOOR_TIMEOUT = 10
# The bridge waits on the panel for the time it is handed; Odoo waits that much
# longer for the bridge, so a slow panel comes back as the bridge's error.
EHOME_BRIDGE_MARGIN = 5


class DeviceDevice(models.Model):
    _inherit = "device.device"

    is_access_device = fields.Boolean(
        compute="_compute_is_access_device",
        store=True,
    )
    access_connection_mode = fields.Selection(
        selection=[
            ("direct", "ISAPI Direct"),
            ("ehome", "EHOME Tunnel"),
        ],
        default="ehome",
        help="How Odoo communicates with the device. "
        "EHOME: device connects outbound to the EHOME server (no port forwarding needed). "
        "Direct: Odoo connects to the device IP via HTTPS/Digest Auth.",
    )
    ehome_device_id = fields.Char(
        string="EHOME Device ID",
        help="Identifier the panel registers with on the EHOME bridge.",
    )
    ehome_bridge_url = fields.Char(
        string="EHOME Bridge URL",
        default=EHOME_BRIDGE_DEFAULT_URL,
    )
    inbound_credential_shared = fields.Boolean(
        compute="_compute_inbound_credential_shared",
        help="The credential that authenticates this device's calls to Odoo is "
        "not a token of its own: it is a device login or an EHOME record, so the "
        "value accepted as its bearer token is a password or the EHOME device id.",
    )

    @api.depends("credential_id.category_id")
    def _compute_inbound_credential_shared(self) -> None:
        bearer = self.env.ref(
            "credential.credential_category_bearer_token", raise_if_not_found=False
        )
        for device in self:
            category = device.sudo().credential_id.category_id
            device.inbound_credential_shared = bool(category) and category != bearer

    def action_rotate_inbound_token(self) -> None:
        self._adopt_legacy_access_credentials()
        for device in self:
            device.credential_id = self._create_inbound_credential(
                device.identifier or device.name, device.company_id.id
            )

    def _adopt_legacy_access_credentials(self) -> None:
        ehome = self.env.ref(
            "device_access_control.credential_category_ehome", raise_if_not_found=False
        )
        basic = self.env.ref(
            "credential.credential_category_basic_auth", raise_if_not_found=False
        )
        for device in self.sudo().filtered("is_access_device"):
            credential = device.credential_id
            if not credential:
                continue
            if ehome and credential.category_id == ehome:
                payload = credential._use_secret_payload("device_access_control:ehome")
                device.write(
                    {
                        "ehome_device_id": device.ehome_device_id
                        or payload.get("api_key")
                        or False,
                        "ehome_bridge_url": payload.get("api_secret")
                        or device.ehome_bridge_url,
                    }
                )
            elif basic and credential.category_id == basic:
                if not device.dial_credential_id:
                    device.dial_credential_id = credential

    access_door_state = fields.Selection(
        selection=[
            ("unknown", "Unknown"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("always_open", "Always Open"),
            ("always_closed", "Locked"),
        ],
        default="unknown",
        readonly=True,
    )
    device_model = fields.Char(help="Device model (e.g. DS-K1T341CMFW).")

    access_verify_mode = fields.Selection(
        selection=[
            ("cardOrFpOrPw", "Card / Fingerprint / Password"),
            ("faceOrFpOrCardOrPw", "Face / Fingerprint / Card / Password"),
            ("fpOrCard", "Fingerprint / Card"),
            ("fp", "Fingerprint Only"),
            ("card", "Card Only"),
            ("face", "Face Only"),
            ("cardOrFaceOrFp", "Card / Face / Fingerprint"),
            ("fpAndCard", "Fingerprint AND Card"),
            ("faceAndFp", "Face AND Fingerprint"),
        ],
        default="cardOrFpOrPw",
    )
    access_schedule_monday = fields.Boolean(default=True)
    access_schedule_tuesday = fields.Boolean(default=True)
    access_schedule_wednesday = fields.Boolean(default=True)
    access_schedule_thursday = fields.Boolean(default=True)
    access_schedule_friday = fields.Boolean(default=True)
    access_schedule_saturday = fields.Boolean(default=True)
    access_schedule_sunday = fields.Boolean(default=True)
    access_schedule_begin_time = fields.Float(default=0.0)
    access_schedule_end_time = fields.Float(default=24.0)
    access_early = fields.Integer(
        default=30,
        help="Minutes before the scheduled start time to allow access. "
        "For example, 30 means employees can enter 30 minutes early. "
        "Only affects the device schedule, not the Odoo calendar.",
    )
    collaborator_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        help="Work schedule pushed to the device for collaborator access (Plan 2). "
        "Defaults to the company's work schedule if not set.",
    )
    schedule_summary = fields.Html(compute="_compute_schedule_summary")

    access_event_ids = fields.One2many(
        comodel_name="access.event",
        inverse_name="device_id",
    )
    access_event_count = fields.Count(count_of="access_event_ids")
    access_command_ids = fields.One2many(
        comodel_name="access.command",
        inverse_name="device_id",
    )
    access_command_count = fields.Count(count_of="access_command_ids")
    access_user_ids = fields.One2many(
        comodel_name="access.device.user",
        inverse_name="device_id",
    )
    access_user_count = fields.Count(count_of="access_user_ids")

    @api.model
    def _device_kind_categories(self, kind):
        codes = super()._device_kind_categories(kind)
        if kind == "access":
            return [*codes, ACCESS_CATEGORY_CODE]
        return codes

    @api.depends("device_category_id", "device_category_id.code")
    def _compute_is_access_device(self) -> None:
        for record in self:
            record.is_access_device = record._is_device_kind("access")

    @api.model
    def _access_device_defaults(self) -> dict:
        ceiling = int(
            self.env.registry.settings.get(
                self.env, "integration.max_payload_size_limit", ACCESS_MAX_PAYLOAD
            )
            or ACCESS_MAX_PAYLOAD
        )
        return {
            "max_payload_size": min(ACCESS_MAX_PAYLOAD, ceiling),
            "log_request_payload_max_bytes": ACCESS_MAX_LOGGED_PAYLOAD,
        }

    @api.model_create_multi
    def create(self, vals_list):
        category = self.env["device.kind"].sudo()
        access_ids = set(category.search([("code", "=", ACCESS_CATEGORY_CODE)]).ids)
        for vals in vals_list:
            if vals.get("device_category_id") in access_ids:
                for key, value in self._access_device_defaults().items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    @api.model
    def _receiver_for_access_device(self, identifier, **path_args):
        return self._receiver_for_identifier(
            identifier, domain=[("device_category_id.code", "=", ACCESS_CATEGORY_CODE)]
        )

    @api.model
    def _prepare_access_device_refusal_response(self, refused):
        """A reader that sees anything but 200 retries the event or stops
        reporting, so a refusal answers as its protocol expects and the
        verdict is in the access log alone."""
        return request.prepare_response("OK", status=200)

    def _inbound_auth_mode(self, parameter_key=None):
        if parameter_key is None and self._is_device_kind("access"):
            parameter_key = AUTH_MODE_PARAM
        return super()._inbound_auth_mode(parameter_key)

    def _inbound_event_logged(self, event_type):
        if event_type in ("command_poll", "access_heartbeat"):
            return False
        return super()._inbound_event_logged(event_type)

    @api.depends(
        "access_early",
        "collaborator_calendar_id.attendance_ids",
        "company_id.resource_calendar_id.attendance_ids",
    )
    def _compute_schedule_summary(self) -> None:
        day_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for record in self:
            if not record.is_access_device:
                record.schedule_summary = False
                continue

            calendar = (
                record.collaborator_calendar_id
                or record.company_id.resource_calendar_id
            )
            early = record.access_early or 0

            collab_lines = []
            if calendar:
                day_slots = {str(i): [] for i in range(7)}
                for att in calendar.attendance_ids:
                    if att.display_type == "line_section":
                        continue
                    day_slots.setdefault(att.dayofweek, []).append(
                        (att.hour_from, att.hour_to)
                    )

                for day_idx in range(7):
                    slots = sorted(day_slots.get(str(day_idx), []))
                    if slots:
                        first_from = slots[0][0] - (early / 60.0)
                        first_from = max(0.0, first_from)
                        last_to = slots[-1][1]
                        collab_lines.append((day_abbr[day_idx], first_from, last_to))

            def _format_time(value):
                hours = int(value)
                mins = int((value - hours) * 60)
                return f"{hours:02d}:{mins:02d}"

            def _group_days(lines):
                if not lines:
                    return "<em>No schedule configured</em>"
                groups = []
                current = {
                    "start_day": lines[0][0],
                    "end_day": lines[0][0],
                    "from": lines[0][1],
                    "to": lines[0][2],
                }
                for day, hf, ht in lines[1:]:
                    if hf == current["from"] and ht == current["to"]:
                        current["end_day"] = day
                    else:
                        groups.append(current)
                        current = {
                            "start_day": day,
                            "end_day": day,
                            "from": hf,
                            "to": ht,
                        }
                groups.append(current)
                parts = []
                for grp in groups:
                    days = (
                        f"{grp['start_day']}-{grp['end_day']}"
                        if grp["start_day"] != grp["end_day"]
                        else grp["start_day"]
                    )
                    parts.append(
                        f"{days}: {_format_time(grp['from'])} - {_format_time(grp['to'])}"
                    )
                return "<br/>".join(parts)

            collab_html = _group_days(collab_lines)
            html = (
                '<div class="d-flex gap-3">'
                '<div class="text-muted small">'
                '<i class="fa fa-clock-o me-1"/><b>Tenant:</b> 24/7'
                "</div>"
                '<div class="text-muted small">'
                f'<i class="fa fa-calendar me-1"/><b>Collaborator:</b> {collab_html}'
                "</div>"
                "</div>"
            )
            record.schedule_summary = html

    _ISAPI_WEEKDAYS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

    _ACCESS_SCHEDULE_DAY_FIELDS = [
        "access_schedule_monday",
        "access_schedule_tuesday",
        "access_schedule_wednesday",
        "access_schedule_thursday",
        "access_schedule_friday",
        "access_schedule_saturday",
        "access_schedule_sunday",
    ]

    @staticmethod
    def _float_to_hms(value) -> str:
        hours = int(value)
        minutes = int((value - hours) * 60)
        seconds = int(((value - hours) * 60 - minutes) * 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _hms_to_float(hms):
        parts = hms.split(":")
        return int(parts[0]) + int(parts[1]) / 60.0 + int(parts[2]) / 3600.0

    def _prepare_day_segments(self):
        self.check_singleton()
        begin = self._float_to_hms(self.access_schedule_begin_time)
        end = self._float_to_hms(self.access_schedule_end_time)

        segments = []
        for idx, day_name in enumerate(self._ISAPI_WEEKDAYS):
            day_enabled = getattr(self, self._ACCESS_SCHEDULE_DAY_FIELDS[idx])
            for seg_id in range(1, 9):
                if seg_id == 1 and day_enabled:
                    segments.append(
                        {
                            "week": day_name,
                            "id": seg_id,
                            "enable": True,
                            "TimeSegment": {
                                "beginTime": begin,
                                "endTime": end,
                            },
                        }
                    )
                else:
                    segments.append(
                        {
                            "week": day_name,
                            "id": seg_id,
                            "enable": False,
                            "TimeSegment": {
                                "beginTime": "00:00:00",
                                "endTime": "00:00:00",
                            },
                        }
                    )
        return segments

    def _prepare_week_plan_cfg(self) -> dict:
        self.check_singleton()
        mode = self.access_verify_mode or "cardOrFpOrPw"
        segments = self._prepare_day_segments()
        for seg in segments:
            seg["verifyMode"] = mode if seg["enable"] else "cardOrFpOrPw"
        return {"VerifyWeekPlanCfg": {"enable": True, "WeekPlanCfg": segments}}

    def _prepare_user_right_week_plan_cfg(self) -> dict:
        self.check_singleton()
        segments = self._prepare_day_segments()
        return {"UserRightWeekPlanCfg": {"enable": True, "WeekPlanCfg": segments}}

    def _prepare_calendar_week_plan(self, calendar):
        early_offset = self.access_early / 60.0 if self.access_early else 0.0
        day_slots = {str(i): [] for i in range(7)}
        for att in calendar.attendance_ids:
            if att.display_type == "line_section":
                continue
            day_slots.setdefault(att.dayofweek, []).append((att.hour_from, att.hour_to))

        segments = []
        for day_idx, day_name in enumerate(self._ISAPI_WEEKDAYS):
            slots = sorted(day_slots.get(str(day_idx), []))
            for seg_id in range(1, 9):
                if seg_id <= len(slots):
                    hour_from = slots[seg_id - 1][0]
                    hour_to = slots[seg_id - 1][1]
                    if seg_id == 1 and early_offset:
                        hour_from = max(0.0, hour_from - early_offset)
                    begin = self._float_to_hms(hour_from)
                    end = self._float_to_hms(hour_to)
                    segments.append(
                        {
                            "week": day_name,
                            "id": seg_id,
                            "enable": True,
                            "TimeSegment": {"beginTime": begin, "endTime": end},
                        }
                    )
                else:
                    segments.append(
                        {
                            "week": day_name,
                            "id": seg_id,
                            "enable": False,
                            "TimeSegment": {
                                "beginTime": "00:00:00",
                                "endTime": "00:00:00",
                            },
                        }
                    )
        return segments

    def _get_collaborator_calendar(self):
        self.check_singleton()
        return self.collaborator_calendar_id or self.company_id.resource_calendar_id

    def action_sync_work_schedule(self):
        self.check_singleton()
        calendar = self._get_collaborator_calendar()
        if not calendar:
            return self._notify(
                self.env._("No Work Schedule"),
                self.env._(
                    "Set a Collaborator Schedule on the device or "
                    "configure a work schedule on the company."
                ),
                "warning",
                True,
            )

        segments = self._prepare_calendar_week_plan(calendar)
        week_plan_payload = json_dumps(
            {"UserRightWeekPlanCfg": {"enable": True, "WeekPlanCfg": segments}}
        )
        plan_template_payload = json_dumps(
            {
                "UserRightPlanTemplate": {
                    "enable": True,
                    "templateName": "Collaborator",
                    "weekPlanNo": 2,
                    "holidayGroupNo": "",
                }
            }
        )

        endpoints = [
            (
                "/ISAPI/AccessControl/UserRightWeekPlanCfg/2?format=json",
                week_plan_payload,
            ),
            (
                "/ISAPI/AccessControl/UserRightPlanTemplate/2?format=json",
                plan_template_payload,
            ),
        ]

        for path, data in endpoints:
            try:
                self._isapi_request(
                    "PUT",
                    path,
                    data=data,
                    content_type="application/json",
                    timeout=30,
                )
            except Exception:
                _logger.exception(
                    "Work schedule sync failed for %s (%s)", self.name, path
                )
                return self._notify(
                    self.env._("Sync Failed"),
                    self.env._("Could not push work schedule to device."),
                    "danger",
                    True,
                )

        return self._notify(
            self.env._("Work Schedule Synced"),
            self.env._(
                "Plan 2 (collaborator hours) synced from '%s'.",
                calendar.name,
            ),
        )

    def action_sync_access_config(self):
        self.check_singleton()

        plan_template_payload = {
            "UserRightPlanTemplate": {
                "enable": True,
                "templateName": "Tenant",
                "weekPlanNo": 1,
                "holidayGroupNo": "",
            }
        }

        endpoints = [
            (
                "/ISAPI/AccessControl/VerifyWeekPlanCfg/1?format=json",
                self._prepare_week_plan_cfg(),
            ),
            (
                "/ISAPI/AccessControl/UserRightWeekPlanCfg/1?format=json",
                self._prepare_user_right_week_plan_cfg(),
            ),
            (
                "/ISAPI/AccessControl/UserRightPlanTemplate/1?format=json",
                plan_template_payload,
            ),
        ]

        for path, payload in endpoints:
            data = json_dumps(payload)
            _logger.info(
                "AccessConfig PUSH: sending %d bytes to %s (%s)",
                len(data),
                self.name,
                path,
            )
            try:
                self._isapi_request(
                    "PUT",
                    path,
                    data=data,
                    content_type="application/json",
                    timeout=30,
                )
                _logger.info("AccessConfig PUSH: OK for %s (%s)", self.name, path)
            except Exception:
                _logger.exception(
                    "AccessConfig PUSH failed for %s (%s)", self.name, path
                )
                return self._notify(
                    self.env._("Sync Failed"),
                    self.env._(
                        "Could not sync configuration. Check server logs for details."
                    ),
                    "danger",
                    True,
                )

        return self._notify(
            self.env._("Access Config Synced"),
            self.env._("Verify mode and access schedule pushed to device."),
        )

    def action_fetch_access_config(self):
        self.check_singleton()
        _logger.info("AccessConfig FETCH: requesting from %s", self.name)

        try:
            resp = self._isapi_request(
                "GET",
                "/ISAPI/AccessControl/VerifyWeekPlanCfg/1?format=json",
                content_type="application/json",
                timeout=30,
            )
            _logger.info("AccessConfig FETCH: response received for %s", self.name)
        except Exception:
            _logger.exception("AccessConfig FETCH failed for %s", self.name)
            return self._notify(
                self.env._("Fetch Failed"),
                self.env._(
                    "Could not fetch configuration. Check server logs for details."
                ),
                "danger",
                True,
            )

        try:
            content = resp.content if hasattr(resp, "content") else resp
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            data = json_loads(content)
        except json.JSONDecodeError, AttributeError:
            _logger.exception(
                "AccessConfig FETCH: failed to parse response for %s", self.name
            )
            return self._notify(
                self.env._("Fetch Failed"),
                self.env._(
                    "Could not parse device response. Check server logs for details."
                ),
                "danger",
                True,
            )

        segments = data.get("VerifyWeekPlanCfg", {}).get("WeekPlanCfg", [])
        _logger.info(
            "AccessConfig FETCH: got %d segments for %s", len(segments), self.name
        )

        vals = {}
        for idx, day_name in enumerate(self._ISAPI_WEEKDAYS):
            seg = next(
                (s for s in segments if s.get("week") == day_name and s.get("id") == 1),
                {},
            )
            vals[self._ACCESS_SCHEDULE_DAY_FIELDS[idx]] = seg.get("enable", False)
            if "access_verify_mode" not in vals and seg.get("enable"):
                ts = seg.get("TimeSegment", {})
                vals["access_verify_mode"] = seg.get("verifyMode", "cardOrFpOrPw")
                vals["access_schedule_begin_time"] = self._hms_to_float(
                    ts.get("beginTime", "00:00:00")
                )
                vals["access_schedule_end_time"] = self._hms_to_float(
                    ts.get("endTime", "00:00:00")
                )

        _logger.info("AccessConfig FETCH: writing vals %s for %s", vals, self.name)
        self.write(vals)

        return self._notify(
            self.env._("Access Config Fetched"),
            self.env._("Verify mode and schedule updated from device."),
        )

    def _require_ehome_device_id(self) -> str:
        self.check_singleton()
        if not self.ehome_device_id:
            raise UserError(self.env._("EHOME Device ID is not configured."))
        return self.ehome_device_id

    def _get_ehome_api_url(self):
        self.check_singleton()
        return self.ehome_bridge_url or EHOME_BRIDGE_DEFAULT_URL

    @api.model
    def get_access_dashboard_data(self) -> dict:
        devices = self.search([("is_access_device", "=", True)])
        event_model = self.env["access.event"]
        today_start = fields.Datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        today_events = event_model.search(
            [
                ("event_time", ">=", today_start),
                ("event_type", "!=", "heartbeat"),
            ]
        )
        access_granted = len(
            today_events.filtered(lambda e: e.event_type == "access_granted")
        )
        access_denied = len(
            today_events.filtered(lambda e: e.event_type == "access_denied")
        )
        alarms = len(today_events.filtered(lambda e: e.event_type == "alarm"))
        total_users = sum(d.access_user_count for d in devices)
        online_count = len(
            devices.filtered(lambda d: d.connection_state == "connected")
        )
        return {
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "model": d.device_model,
                    "state": d.connection_state,
                    "door_state": d.access_door_state,
                    "connection_mode": d.access_connection_mode,
                    "ehome_device_id": d.ehome_device_id or "",
                    "user_count": d.access_user_count,
                    "last_heartbeat": d.date_last_data_received
                    and d.date_last_data_received.isoformat(),
                }
                for d in devices
            ],
            "stats": {
                "devices_online": online_count,
                "devices_total": len(devices),
                "access_granted_today": access_granted,
                "access_denied_today": access_denied,
                "alarms_today": alarms,
                "total_events_today": len(today_events),
                "total_users": total_users,
            },
        }

    def _door_command(self, cmd) -> None:
        self.check_singleton()
        if self.access_connection_mode == "ehome":
            self._ehome_door_command(cmd)
        elif self.dial_credential_id and self.endpoint:
            door_xml = (
                '<DeviceControlDoor xmlns="http://www.isapi.org/ver20/XMLSchema">'
                f"<cmd>{xml_escape(str(cmd))}</cmd>"
                "</DeviceControlDoor>"
            )
            self._isapi_request(
                "PUT",
                "/ISAPI/AccessControl/DeviceControl/door/1",
                data=door_xml,
                content_type="application/xml",
            )
        else:
            self.env["access.command"].create(
                {
                    "device_id": self.id,
                    "command_type": "open_door" if cmd == "open" else "close_door",
                }
            )

    def _ehome_door_command(self, cmd) -> None:
        device_id = self._require_ehome_device_id()
        connection = self._require_connection()
        api_url = connection._base_url()
        try:
            resp = connection._get_api_client().post(
                f"/api/door/{cmd}",
                headers={
                    "X-Device-ID": device_id,
                    "X-ISAPI-Timeout": str(EHOME_DOOR_TIMEOUT),
                },
                timeout=EHOME_DOOR_TIMEOUT + EHOME_BRIDGE_MARGIN,
                raise_for_status=False,
            )
        except CommTimeoutError:
            raise UserError(
                self.env._(
                    "EHOME server did not respond within %d seconds.",
                    EHOME_DOOR_TIMEOUT + EHOME_BRIDGE_MARGIN,
                )
            ) from None
        except CommError:
            raise UserError(
                self.env._("Cannot connect to EHOME server at %s.", api_url)
            ) from None

        if resp["status_code"] != 200:
            raise UserError(
                self.env._("EHOME error: %s", self._ehome_error_detail(resp))
            )

    def action_view_door(self):
        self.check_singleton()
        self._door_command("open")
        self.access_door_state = "open"
        return self._notify(
            self.env._("Door Opened"),
            self.env._("Door opened successfully."),
        )

    def action_close_door(self):
        self.check_singleton()
        self._door_command("close")
        self.access_door_state = "closed"
        return self._notify(
            self.env._("Door Closed"),
            self.env._("Door closed."),
            "info",
        )

    def action_always_close(self):
        self.check_singleton()
        self._door_command("alwaysClose")
        self.access_door_state = "always_closed"
        return self._notify(
            self.env._("Door Locked"),
            self.env._("Door locked. No access will be granted until unlocked."),
            "danger",
            True,
        )

    def action_check_connection(self):
        self.check_singleton()
        if self.access_connection_mode == "ehome":
            self._check_ehome_connection()
        else:
            self._check_direct_connection()
        state_label = dict(self._fields["connection_state"].selection).get(
            self.connection_state,
            self.connection_state,
        )
        return self._notify(
            self.env._("Connection Check"),
            self.env._("Device status: %s", state_label),
            ("success" if self.connection_state == "connected" else "warning"),
        )

    def _check_ehome_connection(self) -> None:
        self._require_ehome_device_id()
        self._require_connection()
        self._check_ehome_status_on_bridge()
        if self.connection_state != "connected" or not self._is_device_info_required():
            return
        try:
            info_resp = self._isapi_request(
                "GET",
                "/ISAPI/System/deviceInfo",
                timeout=10,
            )
            self._update_device_info_from_response(info_resp)
        except UserError:
            _logger.debug("Could not auto-fetch device info for %s", self.name)

    def _check_direct_connection(self) -> None:
        try:
            resp = self._isapi_request("GET", "/ISAPI/System/deviceInfo", timeout=5)
            self.write(
                {
                    "connection_state": "connected",
                    "date_last_data_received": fields.Datetime.now(),
                }
            )
            if self._is_device_info_required():
                self._update_device_info_from_response(resp)
        except UserError:
            self.write({"connection_state": "disconnected"})

    _DEVICE_INFO_FIELDS = (
        ("model", "device_model"),
        ("serialNumber", "serial_number"),
    )

    def _update_device_info_from_response(self, resp) -> None:
        try:
            root = ET.fromstring(resp.content if hasattr(resp, "content") else resp)
        except ET.ParseError:
            _logger.warning("Could not parse deviceInfo XML from %s", self.name)
            return
        vals = {}
        for tag, field_name in self._DEVICE_INFO_FIELDS:
            value = find_text(root, tag)
            if value:
                vals[field_name] = value
        if vals:
            self.write(vals)
        else:
            _logger.warning(
                "deviceInfo from %s carried none of %s",
                self.name,
                ", ".join(tag for tag, _ in self._DEVICE_INFO_FIELDS),
            )

    def _is_device_info_required(self) -> bool:
        return not self.serial_number or not self.device_model

    def action_get_device_info(self):
        self.check_singleton()
        resp = self._isapi_request("GET", "/ISAPI/System/deviceInfo", timeout=10)
        self._update_device_info_from_response(resp)
        return self._notify(
            self.env._("Device Info"),
            self.env._(
                "Device info updated: %(model)s %(serial)s",
                model=self.device_model or "",
                serial=self.serial_number or "",
            ),
        )

    def action_fetch_users(self):
        self.check_singleton()
        device_user_model = self.env["access.device.user"]
        # asked before the device is, so a refused caller never reaches it
        # with its credentials
        device_user_model.check_access("create")
        users_data = self._get_all_device_users()
        if not users_data:
            return self._notify(
                self.env._("No Users Found"),
                self.env._("No users registered on the device."),
                "warning",
            )

        created = 0
        updated = 0
        unmatched_names = []
        employee_model = self.env["hr.employee"].sudo()

        for user_info in users_data:
            employee_no = str(user_info.get("employeeNo", "")).strip()
            if not employee_no:
                continue

            right_plan = user_info.get("RightPlan", [{}])
            plan_no = (
                str(right_plan[0].get("planTemplateNo", "1")) if right_plan else "1"
            )
            access_profile = "tenant" if plan_no == "1" else "collaborator"

            biometric_vals = {
                "fingerprint_count": user_info.get("numOfFP", 0),
                "face_count": user_info.get("numOfFace", 0),
                "card_no": str(user_info.get("cardNo", "")).strip() or False,
                "access_profile": access_profile,
                "synced_date": fields.Datetime.now(),
            }

            existing = device_user_model.search(
                [
                    ("device_id", "=", self.id),
                    ("employee_no", "=", employee_no),
                ],
                limit=1,
            )
            if existing:
                existing.write(biometric_vals)
                updated += 1
                continue

            employee = employee_model.search([("barcode", "=", employee_no)], limit=1)
            if not employee:
                try:
                    employee = employee_model.browse(int(employee_no)).exists()
                except ValueError, TypeError:
                    employee = employee_model

            vals = {
                "device_id": self.id,
                "employee_no": employee_no,
                "state": "synced",
                **biometric_vals,
            }
            if employee:
                vals["employee_id"] = employee.id
            else:
                unmatched_names.append(user_info.get("name", employee_no))

            device_user_model.create(vals)
            created += 1

        parts = []
        if created:
            parts.append(self.env._("%s users imported.", created))
        if updated:
            parts.append(self.env._("%s users updated.", updated))
        if unmatched_names:
            parts.append(
                self.env._(
                    "%(count)s without employee match: %(names)s",
                    count=len(unmatched_names),
                    names=", ".join(unmatched_names[:10]),
                )
            )

        return self._notify(
            self.env._("Fetch Users Complete"),
            " ".join(parts) or self.env._("Nothing to import."),
            "success" if created or updated else "info",
            bool(unmatched_names),
        )

    def _get_all_device_users(self):
        self.check_singleton()
        all_users = []
        position = 0
        page_size = 30

        while True:
            payload = json_dumps(
                {
                    "UserInfoSearchCond": {
                        "searchID": "1",
                        "searchResultPosition": position,
                        "maxResults": page_size,
                    }
                }
            )

            try:
                resp = self._isapi_request(
                    "POST",
                    "/ISAPI/AccessControl/UserInfo/Search?format=json",
                    data=payload,
                    content_type="application/json",
                    timeout=30,
                )
            except Exception:
                _logger.exception("Failed to fetch users from device %s", self.name)
                break

            content = resp.content if hasattr(resp, "content") else resp
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")

            try:
                data = json_loads(content)
            except json.JSONDecodeError, TypeError:
                _logger.warning(
                    "Failed to parse user search response from %s", self.name
                )
                break

            info = data.get("UserInfoSearch", {})
            users = info.get("UserInfo", [])
            total = int(info.get("totalMatches", 0))

            all_users.extend(users)
            position += len(users)

            if position >= total or not users:
                break

        _logger.info("Fetched %s users from device %s", len(all_users), self.name)
        return all_users

    def action_view_events(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Events"),
            "res_model": "access.event",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    def action_view_commands(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Commands"),
            "res_model": "access.command",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    def action_view_users(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Device Users"),
            "res_model": "access.device.user",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    def _isapi_request(
        self, method, path, data=None, content_type="application/json", timeout=10
    ):
        self.check_singleton()
        if self.access_connection_mode == "ehome":
            return self._isapi_via_ehome(method, path, data, content_type, timeout)
        return self._isapi_direct(method, path, data, content_type, timeout)

    def _isapi_via_ehome(
        self, method, path, data=None, content_type="application/json", timeout=10
    ):
        device_id = self._require_ehome_device_id()

        connection = self._require_connection()
        api_url = connection._base_url()
        headers = {
            "X-ISAPI-Method": method,
            "X-ISAPI-URL": path,
            "X-Device-ID": device_id,
            "X-ISAPI-Timeout": str(timeout),
        }
        if content_type:
            headers["Content-Type"] = content_type

        try:
            resp = connection._get_api_client().post(
                "/api/isapi",
                headers=headers,
                data=data,
                timeout=timeout + EHOME_BRIDGE_MARGIN,
                raw=True,
                raise_for_status=False,
            )
        except CommTimeoutError:
            raise UserError(
                self.env._(
                    "EHOME server did not respond within %d seconds.",
                    timeout + EHOME_BRIDGE_MARGIN,
                )
            ) from None
        except CommError:
            raise UserError(
                self.env._("Cannot connect to EHOME server at %s.", api_url)
            ) from None

        if resp.status_code != 200:
            error_data = (
                resp.json()
                if resp.headers.get("Content-Type", "").startswith("application/json")
                else {}
            )
            raise UserError(
                self.env._(
                    "EHOME ISAPI error: %s", error_data.get("error", resp.text[:500])
                )
            )
        return self._unwrap_ehome_response(resp)

    @staticmethod
    def _ehome_error_detail(resp):
        body = resp["body"]
        if isinstance(body, dict):
            return body.get("error") or json_dumps(body)[:200]
        return str(body)[:200]

    def _unwrap_ehome_response(self, resp) -> ISAPIResponse:
        # The bridge answers 200 with the panel's bytes in base64; it cannot
        # tell their type, so the content says what it is.
        try:
            content = base64.b64decode(resp.json()["response"], validate=True)
        except ValueError, KeyError, TypeError:
            raise UserError(
                self.env._(
                    "The EHOME bridge answered without the panel's response: %s",
                    resp.text[:200],
                )
            ) from None
        return ISAPIResponse(
            content=content, headers={"Content-Type": isapi_content_type(content)}
        )

    def _isapi_direct(
        self, method, path, data=None, content_type="application/json", timeout=10
    ):
        if not self.endpoint:
            raise UserError(self.env._("Device IP is not configured."))
        if not self.dial_credential_id:
            raise UserError(self.env._("Device login is not configured."))

        credential = self.dial_credential_id.sudo()
        if not credential._use_basic_auth("device_access_control:isapi"):
            raise UserError(self.env._("Credential is missing username or password."))

        connection = self._require_connection()
        headers = {"Content-Type": content_type}

        try:
            resp = connection._get_api_client().request(
                method,
                path,
                data=data,
                headers=headers,
                timeout=timeout,
                raw=True,
                raise_for_status=False,
            )
        except CommTimeoutError:
            raise UserError(
                self.env._("Device did not respond within %d seconds.", timeout)
            ) from None
        except CommError:
            raise UserError(
                self.env._("Cannot connect to device at %s.", self.endpoint)
            ) from None

        if resp.status_code >= 400:
            raise UserError(
                self.env._(
                    "Device returned error %(status)s: %(body)s",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
            )

        return resp

    @api.model
    def _cron_check_ehome_status(self) -> None:
        ehome_devices = self.search(
            [
                ("is_access_device", "=", True),
                ("access_connection_mode", "=", "ehome"),
            ]
        )
        if not ehome_devices:
            return

        for devices in ehome_devices.grouped(
            lambda device: device._get_ehome_api_url()
        ).values():
            devices._check_ehome_status_on_bridge()

    def _check_ehome_status_on_bridge(self) -> None:
        # Being listed by the bridge is the panel's sign of life: it refreshes
        # date_last_data_received, which the health cron reads.
        try:
            client = self[:1]._require_connection()._get_api_client()
            body = client.get("/api/devices", timeout=5)["body"]
            connected = body.get("devices", {}) if isinstance(body, dict) else {}
        except CommError, UserError:
            _logger.debug(
                "Cannot reach EHOME server at %s for status check",
                self[:1]._get_ehome_api_url(),
            )
            self._set_connection_state("error")
            return
        listed = self.filtered(lambda device: device.ehome_device_id in connected)
        listed._set_connection_state("connected", when=fields.Datetime.now())
        (self - listed)._set_connection_state("disconnected")
