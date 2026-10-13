import base64
import binascii
import hashlib
import logging

from werkzeug.wrappers import Response

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.integration.tools.admission import Acknowledged, Resolution

_logger = logging.getLogger(__name__)

DAV_API_KEY_SCOPE = "dav"

DAV_CATEGORY_CODE = "dav_client"
DAV_DEVICE_DOMAIN = [
    ("dav_sync_enabled", "=", True),
    ("active", "=", True),
    ("dav_user_id", "!=", False),
]
DAV_CHALLENGE = {"WWW-Authenticate": 'Basic realm="Odoo DAV"'}


class DeviceDevice(models.Model):
    _inherit = "device.device"

    is_dav_device = fields.Boolean(
        string="Is DAV Client",
        compute="_compute_is_dav_device",
        store=True,
        help="Whether this device uses CalDAV/CardDAV sync",
    )
    dav_sync_enabled = fields.Boolean(
        string="DAV Sync Enabled",
        default=False,
        tracking=True,
        help="Enable CalDAV/CardDAV synchronization for this device",
    )
    dav_user_id = fields.Many2one(
        comodel_name="res.users",
        string="DAV User Account",
        tracking=True,
        help="User account for DAV authentication and data access",
    )
    dav_addressbook_enabled = fields.Boolean(
        string="Sync Contacts (CardDAV)",
        default=True,
        help="Enable CardDAV contact synchronization",
    )
    dav_calendar_enabled = fields.Boolean(
        string="Sync Calendar (CalDAV)",
        default=True,
        help="Enable CalDAV calendar synchronization",
    )

    dav_last_sync = fields.Datetime(
        string="Last DAV Sync",
        readonly=True,
        help="Last successful sync timestamp",
    )
    dav_addressbook_ctag = fields.Char(
        string="Addressbook CTag",
        compute="_compute_dav_addressbook_ctag",
        help="Collection tag for addressbook (changes when contacts modified)",
    )
    dav_calendar_ctag = fields.Char(
        string="Calendar CTag",
        compute="_compute_dav_calendar_ctag",
        help="Collection tag for calendar (changes when events modified)",
    )

    dav_sync_state_ids = fields.One2many(
        comodel_name="dav.sync.state",
        inverse_name="device_id",
        string="DAV Sync States",
        help="Sync state for individual resources (contacts/events)",
    )
    dav_sync_state_count = fields.Count(
        count_of="dav_sync_state_ids",
        string="Sync State Count",
    )

    @api.model
    def _device_kind_categories(self, kind):
        codes = super()._device_kind_categories(kind)
        if kind == "dav":
            return [*codes, DAV_CATEGORY_CODE]
        return codes

    @api.model
    def _receiver_for_dav(self, **path_args):
        header = request.httprequest.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
            device = self._find_by_inbound_token(token, domain=DAV_DEVICE_DOMAIN)[:1]
            if not device:
                fingerprint = hashlib.sha256(token.encode()).hexdigest()[:12]
                return Resolution(self.browse(), claimed=f"bearer sha256:{fingerprint}")
            return Resolution(device, {"user": device.dav_user_id})
        if header.startswith("Basic "):
            try:
                raw = base64.b64decode(header[6:].strip()).decode("utf-8")
            except binascii.Error, ValueError:
                return Resolution(self.browse(), claimed="basic (undecodable)")
            login, sep, secret = raw.partition(":")
            if not (login and sep and secret):
                return Resolution(
                    self.browse(), claimed="basic (no login and password)"
                )
            user = self.env["res.users"].sudo().search([("login", "=", login)], limit=1)
            device = (
                self.sudo().search(
                    [*DAV_DEVICE_DOMAIN, ("dav_user_id", "=", user.id)], limit=1
                )
                if user
                else self.browse()
            )
            if not device:
                return Resolution(self.browse(), claimed=f"basic login {login}")

            def is_request_authorized(headers, body) -> bool:
                return (
                    self.env["res.users.apikeys"]._get_user_id_for_key(
                        scope=DAV_API_KEY_SCOPE, key=secret
                    )
                    == user.id
                )

            return Resolution(device, {"user": user}, verify=is_request_authorized)
        challenge = Acknowledged("Unauthorized", 401)
        challenge.response.headers.update(DAV_CHALLENGE)
        raise challenge

    @api.model
    def _prepare_dav_refusal_response(self, refused):
        if refused.status in (401, 404):
            return Response("Unauthorized", status=401, headers=DAV_CHALLENGE)
        return Response(refused.reason, status=refused.status)

    @api.depends("device_category_id", "device_category_id.code", "dav_sync_enabled")
    def _compute_is_dav_device(self) -> None:
        for device in self:
            device.is_dav_device = (
                device._is_device_kind("dav") or device.dav_sync_enabled
            )

    @api.depends("dav_user_id", "dav_user_id.partner_id.write_date")
    def _compute_dav_addressbook_ctag(self) -> None:
        users = self.dav_user_id
        latest = dict(
            self.env["res.partner"]._read_group(
                [("user_id", "in", users.ids)], ["user_id"], ["write_date:max"]
            )
        )
        for device in self:
            device.dav_addressbook_ctag = device._dav_ctag(
                latest.get(device.dav_user_id)
            )

    @api.depends("dav_user_id")
    def _compute_dav_calendar_ctag(self) -> None:
        users = self.dav_user_id
        Event = self.env["calendar.event"]
        organized = dict(
            Event._read_group(
                [("user_id", "in", users.ids)], ["user_id"], ["write_date:max"]
            )
        )
        attended = dict(
            Event._read_group(
                [("partner_ids", "in", users.partner_id.ids)],
                ["partner_ids"],
                ["write_date:max"],
            )
        )
        for device in self:
            user = device.dav_user_id
            moments = [organized.get(user), attended.get(user.partner_id)]
            device.dav_calendar_ctag = device._dav_ctag(
                max((moment for moment in moments if moment), default=None)
            )

    def _dav_ctag(self, latest_write) -> str | bool:
        if not self.dav_user_id:
            return False
        if not latest_write:
            return "empty"
        return hashlib.md5(str(latest_write).encode()).hexdigest()[:16]

    def action_view_dav_sync_states(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": "DAV Sync States",
            "res_model": "dav.sync.state",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    def action_generate_dav_password(self) -> dict:
        self.check_singleton()
        device = self.sudo()
        if device.dav_user_id != self.env.user:
            raise UserError(
                self.env._(
                    "A DAV password is the user's own: log in as %(user)s to "
                    "generate one for this device.",
                    user=device.dav_user_id.display_name or "the device's user",
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generate a DAV Password"),
            "res_model": "wizard.res.users.apikeys.create",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_scope_id": self.env.ref(
                    "device_dav_sync.apikeys_scope_dav"
                ).id,
                "default_name": self.env._("DAV: %(device)s", device=device.name),
            },
        }

    def action_force_dav_sync(self) -> dict:
        self.check_singleton()
        if not self.dav_sync_enabled:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "DAV Sync Disabled",
                    "message": "Please enable DAV sync first",
                    "type": "warning",
                },
            }

        self.dav_sync_state_ids.write({"sync_status": "pending"})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sync Triggered",
                "message": f"Marked {len(self.dav_sync_state_ids)} resources for re-sync",
                "type": "success",
            },
        }
