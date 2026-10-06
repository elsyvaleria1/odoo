import base64
import json
import logging
from xml.sax.saxutils import escape as xml_escape

import defusedxml.ElementTree as ET

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from ..tools import find_text

_logger = logging.getLogger(__name__)


class AccessDeviceUser(models.Model):
    _name = "access.device.user"
    _description = "Access Device User"

    device_id = fields.Many2one(
        comodel_name="device.device",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        ondelete="set null",
    )
    employee_no = fields.Char(
        required=True,
        help="employeeNo used in the access device.",
    )
    access_profile = fields.Selection(
        selection=[
            ("tenant", "Tenant"),
            ("collaborator", "Collaborator"),
        ],
        default="collaborator",
        required=True,
        help="Tenant: 24/7 unrestricted access (planTemplateNo=1). "
        "Collaborator: access only during work hours from resource.calendar (planTemplateNo=2).",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("synced", "Synced"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
    )
    fingerprint_count = fields.Integer(readonly=True)
    face_count = fields.Integer(readonly=True)
    face_photo = fields.Binary(attachment=True)
    synced_date = fields.Datetime(readonly=True)
    error_message = fields.Text(readonly=True)
    card_no = fields.Char(help="Access card number for this employee.")

    _device_employee_no_uniq = models.Constraint(
        "UNIQUE (device_id, employee_no)",
        "This employee number is already registered on this device!",
    )

    @api.depends("employee_id", "employee_no")
    def _compute_display_name(self):
        for rec in self:
            if rec.employee_id:
                rec.display_name = rec.employee_id.name
            else:
                rec.display_name = f"#{rec.employee_no} (unmatched)"

    @api.onchange("employee_id")
    def _onchange_employee_id(self) -> None:
        for rec in self:
            if rec.employee_id:
                rec.employee_no = str(rec.employee_id.id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("employee_id"):
                vals["employee_no"] = str(vals["employee_id"])
        records = super().create(vals_list)
        for rec in records:
            if rec.device_id.connection_state == "connected":
                try:
                    rec.action_sync_to_device()
                except UserError:
                    _logger.warning(
                        "Auto-sync failed for %s on creation, will retry later",
                        rec.display_name,
                    )
        return records

    @api.ondelete(at_uninstall=False)
    def _unlink_except_user_on_device(self) -> None:
        for rec in self:
            if rec.employee_no and rec.state != "draft":
                if rec.card_no:
                    try:
                        rec._remove_card_from_device()
                    except UserError:
                        _logger.warning(
                            "Could not delete card for %s before deletion, proceeding anyway",
                            rec.display_name,
                        )
                rec._remove_user_from_device()

    def _update_state_error(self, message) -> None:
        self.write(
            {
                "state": "error",
                "error_message": message,
            }
        )

    def _update_state_synced(self) -> None:
        self.write(
            {
                "state": "synced",
                "synced_date": fields.Datetime.now(),
                "error_message": False,
            }
        )

    def _get_plan_template_no(self) -> str:
        return "1" if self.access_profile == "tenant" else "2"

    def _prepare_user_info_payload(self) -> dict:
        self.check_singleton()
        name = self.employee_id.name if self.employee_id else f"User {self.employee_no}"
        return {
            "employeeNo": self.employee_no or str(self.employee_id.id),
            "name": name,
            "userType": "normal",
            "Valid": {
                "enable": True,
                "beginTime": "2020-01-01T00:00:00",
                "endTime": "2037-12-31T23:59:59",
            },
            "doorRight": "1",
            "RightPlan": [
                {
                    "doorNo": 1,
                    "planTemplateNo": self._get_plan_template_no(),
                }
            ],
        }

    def action_sync_to_device(self):
        self.check_singleton()
        employee = self.employee_id
        employee_no = self.employee_no or str(employee.id)

        payload = {"UserInfo": self._prepare_user_info_payload()}

        if self.state == "draft":
            path = "/ISAPI/AccessControl/UserInfo/Record?format=json"
            method = "POST"
        else:
            path = "/ISAPI/AccessControl/UserInfo/Modify?format=json"
            method = "PUT"

        try:
            self.device_id._isapi_request(
                method,
                path,
                data=json_dumps(payload),
                content_type="application/json",
            )
        except UserError as exc:
            self._update_state_error(str(exc))
            return None
        except Exception as exc:
            _logger.exception("ISAPI sync failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return None

        self.write(
            {
                "employee_no": employee_no,
                "state": "synced",
                "synced_date": fields.Datetime.now(),
                "error_message": False,
            }
        )

        if employee.barcode != employee_no:
            employee.sudo().write({"barcode": employee_no})

        return self.device_id._notify(
            self.env._("User Synced"),
            self.env._("Employee %s synced to device.", employee.name),
        )

    def action_capture_fingerprint(self):
        self.check_singleton()
        if self.state != "synced":
            raise UserError(
                self.env._("Sync the user to the device before capturing fingerprints.")
            )

        employee_no = self.employee_no
        finger_id = self.fingerprint_count + 1

        capture_xml = (
            '<CaptureFingerPrint xmlns="http://www.isapi.org/ver20/XMLSchema">'
            f"<employeeNo>{xml_escape(str(employee_no))}</employeeNo>"
            f"<fingerNo>{xml_escape(str(finger_id))}</fingerNo>"
            "</CaptureFingerPrint>"
        )

        try:
            capture_resp = self.device_id._isapi_request(
                "POST",
                "/ISAPI/AccessControl/CaptureFingerPrint",
                data=capture_xml,
                content_type="application/xml",
                timeout=60,
            )
        except Exception as exc:
            _logger.exception("Fingerprint capture failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Fingerprint Capture Failed"),
                str(exc),
                "danger",
                True,
            )

        finger_data = self._parse_finger_data(capture_resp)
        if not finger_data:
            msg = "No fingerprint data returned from device."
            self._update_state_error(msg)
            return self.device_id._notify(
                self.env._("Fingerprint Capture Failed"),
                msg,
                "danger",
                True,
            )

        register_payload = {
            "FingerPrintCfg": {
                "employeeNo": employee_no,
                "enableCardReader": [1],
                "fingerPrintID": finger_id,
                "fingerType": "normalFP",
                "fingerData": finger_data,
            }
        }

        try:
            self.device_id._isapi_request(
                "POST",
                "/ISAPI/AccessControl/FingerPrint/SetUp?format=json",
                data=json_dumps(register_payload),
                content_type="application/json",
            )
        except Exception as exc:
            _logger.exception(
                "Fingerprint registration failed for %s", self.display_name
            )
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Fingerprint Registration Failed"),
                str(exc),
                "danger",
                True,
            )

        self.write(
            {
                "fingerprint_count": finger_id,
                "error_message": False,
            }
        )

        return self.device_id._notify(
            self.env._("Fingerprint Captured"),
            self.env._("Fingerprint #%d registered successfully.", finger_id),
        )

    def action_capture_face(self):
        self.check_singleton()
        if self.state != "synced":
            raise UserError(
                self.env._("Sync the user to the device before capturing face.")
            )

        if self.device_id.access_connection_mode == "ehome":
            return self._register_face_from_upload()
        return self._capture_face_from_device()

    def _register_face_from_upload(self):
        if not self.face_photo:
            raise UserError(
                self.env._(
                    "Upload a face photo first. EHOME mode cannot capture from the device camera."
                )
            )

        face_data = base64.b64decode(self.face_photo)

        try:
            self._register_face_in_device(face_data)
        except Exception as exc:
            _logger.exception("Face registration failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Face Registration Failed"),
                str(exc),
                "danger",
                True,
            )

        self.write(
            {
                "face_count": self.face_count + 1,
                "error_message": False,
            }
        )

        return self.device_id._notify(
            self.env._("Face Registered"),
            self.env._("Face photo registered on device successfully."),
        )

    def _capture_face_from_device(self):
        capture_xml = (
            '<CaptureFaceDataCond xmlns="http://www.isapi.org/ver20/XMLSchema">'
            "<captureInfrared>true</captureInfrared>"
            "<dataType>binary</dataType>"
            "</CaptureFaceDataCond>"
        )

        try:
            resp = self.device_id._isapi_request(
                "POST",
                "/ISAPI/AccessControl/CaptureFaceData",
                data=capture_xml,
                content_type="application/xml",
                timeout=30,
            )
        except Exception as exc:
            _logger.exception("Face capture failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Face Capture Failed"),
                str(exc),
                "danger",
                True,
            )

        face_data = self._parse_face_data(resp)
        if not face_data:
            msg = self.env._(
                "No face data returned from device. Ensure someone is in front of the camera."
            )
            self._update_state_error(msg)
            return self.device_id._notify(
                self.env._("Face Capture Failed"),
                msg,
                "danger",
                True,
            )

        try:
            self._register_face_in_device(face_data)
        except Exception as exc:
            _logger.exception("Face registration failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Face Registration Failed"),
                str(exc),
                "danger",
                True,
            )

        self.write(
            {
                "face_photo": base64.b64encode(face_data),
                "face_count": self.face_count + 1,
                "error_message": False,
            }
        )

        return self.device_id._notify(
            self.env._("Face Captured"),
            self.env._("Face photo captured and registered successfully."),
        )

    def _register_face_in_device(self, face_data) -> None:
        self.check_singleton()

        user_info = json_dumps({"UserInfo": self._prepare_user_info_payload()})

        boundary = "MIME_boundary"
        body = (
            (
                f"--{boundary}\r\n"
                f"Content-Type: application/json\r\n"
                f'Content-Disposition: form-data; name="UserInfo"\r\n\r\n'
                f"{user_info}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: image/jpeg\r\n"
                f'Content-Disposition: form-data; name="FaceImage"; filename="face.jpg"\r\n\r\n'
            ).encode()
            + face_data
            + f"\r\n--{boundary}--\r\n".encode()
        )

        self.device_id._isapi_request(
            "PUT",
            "/ISAPI/AccessControl/UserInfo/SetUp?format=json",
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def action_remove_from_device(self):
        self.check_singleton()
        if self.card_no:
            try:
                self._remove_card_from_device()
            except UserError:
                _logger.warning(
                    "Could not delete card for %s, proceeding with user removal",
                    self.display_name,
                )
        try:
            self._remove_user_from_device()
        except Exception as exc:
            _logger.exception("User removal failed for %s", self.display_name)
            self._update_state_error(str(exc))
            return None

        self.write(
            {
                "state": "draft",
                "fingerprint_count": 0,
                "face_count": 0,
                "face_photo": False,
                "card_no": False,
                "synced_date": False,
                "error_message": False,
            }
        )

        return self.device_id._notify(
            self.env._("User Removed"),
            self.env._("User removed from device."),
            "warning",
        )

    def _remove_user_from_device(self) -> None:
        self.check_singleton()
        payload = json_dumps(
            {
                "UserInfoDelCond": {
                    "EmployeeNoList": [
                        {"employeeNo": self.employee_no},
                    ],
                }
            }
        )
        response = self.device_id._isapi_request(
            "PUT",
            "/ISAPI/AccessControl/UserInfo/Delete?format=json",
            data=payload,
            content_type="application/json",
        )
        status_code = self._parse_isapi_status_code(response)
        if status_code is not None and status_code != 1:
            raise UserError(
                self.env._(
                    "Device rejected user deletion for %(user)s (statusCode=%(status)s).",
                    user=self.display_name,
                    status=status_code,
                )
            )

    def _remove_card_from_device(self) -> None:
        self.check_singleton()
        if not self.card_no:
            return
        payload = {
            "CardInfoDelCond": {
                "CardNoList": [
                    {"cardNo": self.card_no},
                ],
            }
        }
        self.device_id._isapi_request(
            "PUT",
            "/ISAPI/AccessControl/CardInfo/Delete?format=json",
            data=json_dumps(payload),
            content_type="application/json",
        )

    def action_register_card(self):
        self.check_singleton()
        if self.state != "synced":
            raise UserError(
                self.env._("Sync the user to the device before registering a card.")
            )
        if not self.card_no:
            raise UserError(self.env._("Enter a card number first."))

        payload = {
            "CardInfo": {
                "employeeNo": self.employee_no,
                "cardNo": self.card_no,
                "cardType": "normalCard",
            }
        }

        try:
            self.device_id._isapi_request(
                "POST",
                "/ISAPI/AccessControl/CardInfo/Record?format=json",
                data=json_dumps(payload),
                content_type="application/json",
            )
        except UserError as exc:
            self._update_state_error(str(exc))
            return self.device_id._notify(
                self.env._("Card Registration Failed"),
                str(exc),
                "danger",
                True,
            )

        self.write({"error_message": False})

        return self.device_id._notify(
            self.env._("Card Registered"),
            self.env._("Card %s registered on device.", self.card_no),
        )

    @staticmethod
    def _parse_isapi_status_code(response):
        content = response.content if hasattr(response, "content") else response
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        try:
            data = json_loads(content)
        except json.JSONDecodeError, TypeError:
            return None
        return data.get("statusCode") if isinstance(data, dict) else None

    @staticmethod
    def _parse_finger_data(response):
        try:
            if hasattr(response, "content"):
                text = response.content.decode("utf-8", errors="replace")
            elif isinstance(response, bytes):
                text = response.decode("utf-8", errors="replace")
            else:
                text = str(response)

            root = ET.fromstring(text)
            return find_text(root, ".//fingerData") or None
        except ET.ParseError:
            _logger.warning("Failed to parse fingerprint XML response")
        return None

    @staticmethod
    def _parse_face_data(response):
        if hasattr(response, "content"):
            content = response.content
            content_type = response.headers.get("Content-Type", "")
        else:
            return None

        if "multipart" in content_type:
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part.split("=", 1)[1].strip('"')
                    break
            if boundary:
                parts = content.split(f"--{boundary}".encode())
                for part in parts:
                    if b"image/jpeg" in part or b"image/png" in part:
                        idx = part.find(b"\r\n\r\n")
                        if idx != -1:
                            return part[idx + 4 :].rstrip(b"\r\n--")
        elif b"\xff\xd8" in content[:4]:
            return content

        return None

    @api.model
    def _cron_retry_sync(self) -> None:
        users = self.search(
            [
                ("state", "in", ["draft", "error"]),
                ("device_id.connection_state", "=", "connected"),
            ],
            limit=50,
        )
        for user in users:
            try:
                user.action_sync_to_device()
            except UserError:
                _logger.warning("Cron retry sync failed for %s", user.display_name)
