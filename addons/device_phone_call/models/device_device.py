from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.phone_call.models.phone_call import number_key

COMPANION_SERVICE = "remote_mobile"

PBX_CATEGORY_CODE = "pbx"

_CALL_REPORTER_MAX_PAYLOAD = 52428800
_CALL_REPORTER_MAX_LOGGED_PAYLOAD = 65536


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _receiver_privileges = ("device_phone_call.privilege_file_device_call",)

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Phone user",
        domain="[('share', '=', False)]",
        help="Who carries this handset or answers this line; becomes the "
        "responsible of every call it reports",
    )

    @api.constrains("user_id", "company_id")
    def _check_user_company(self) -> None:
        for device in self.filtered("user_id"):
            if (
                device.company_id
                and device.company_id not in device.user_id.company_ids
            ):
                raise ValidationError(
                    self.env._(
                        "%(user)s has no access to %(company)s, the company of "
                        "phone %(device)s.",
                        user=device.user_id.name,
                        company=device.company_id.name,
                        device=device.display_name,
                    )
                )

    @api.model
    def _call_reporter_category_codes(self) -> set:
        return {PBX_CATEGORY_CODE}

    def _reports_calls(self) -> bool:
        self.check_singleton()
        return self.device_category_id.code in self._call_reporter_category_codes()

    @api.model_create_multi
    def create(self, vals_list):
        reporters = (
            self.env["device.kind"]
            .search([("code", "in", list(self._call_reporter_category_codes()))])
            .ids
        )
        for vals in vals_list:
            if vals.get("device_category_id") not in reporters:
                continue
            vals.setdefault("max_payload_size", _CALL_REPORTER_MAX_PAYLOAD)
            vals.setdefault(
                "log_request_payload_max_bytes", _CALL_REPORTER_MAX_LOGGED_PAYLOAD
            )
            vals.setdefault("duplicate_detection_enabled", True)
            vals.setdefault("duplicate_window_seconds", 900)
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if "device_category_id" in vals:
            self._place_receiver()
        return result

    def _place_receiver(self) -> None:
        super()._place_receiver()
        Gate = self.env["mixin.inbound.gate"]
        for device in self.filtered(
            lambda device: device.active and device._phone_call_channel() == "pbx"
        ):
            lines = device._phone_call_lines()
            Gate._place_principal_in_companies(
                device._inbound_service_user(),
                self.env["res.company"].union(*lines.values()),
            )

    def action_connect(self):
        self.check_singleton()
        if not self._reports_calls():
            return super().action_connect()
        self._set_connection_state("connected", False)
        return None

    def action_read_data(self):
        self.check_singleton()
        if not self._reports_calls():
            return super().action_read_data()
        return None

    def _phone_call_lines(self) -> dict:
        self.check_singleton()
        if self._phone_call_channel() != "pbx":
            return {}
        lines = defaultdict(lambda: self.env["res.company"])
        for company in (
            self.env["res.company"].sudo().search([("phone_ids", "!=", False)])
        ):
            for phone in company.phone_ids:
                key = number_key(phone.sanitized or phone.number)
                if key:
                    lines[key] |= company
        return dict(lines)

    def _phone_call_company(self, line=None, lines=None):
        self.check_singleton()
        own = self.company_id or self.user_id.company_id or self.env.company
        key = number_key(line)
        if key:
            if lines is None:
                lines = self._phone_call_lines()
            owners = lines.get(key)
            if owners:
                return own if own in owners else owners.sorted("id")[:1]
        return own

    def _phone_call_channel(self) -> str:
        self.check_singleton()
        if self.device_category_id.code == PBX_CATEGORY_CODE:
            return "pbx"
        return "mobile"

    @api.model
    def _prepare_companion_refusal_response(self, refused):
        return request.prepare_json_response(
            {"service": COMPANION_SERVICE, **refused.problem()}, status=refused.status
        )
