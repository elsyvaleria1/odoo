import logging
import secrets
import time
from datetime import timedelta
from typing import Self
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.http import request

from odoo.addons.integration.tools.admission import Acknowledged, Refused
from odoo.addons.integration.tools.authentication import is_bearer_token_valid

_logger = logging.getLogger(__name__)

IOT_TOKEN_VALIDITY = timedelta(minutes=15)

# A box runs upstream's iot_drivers, which the box image pulls from
# github.com/odoo/odoo and which presents its paired token on /iot/setup only:
# every other call names the box and proves nothing. Such a call is heard and
# reported once per box, route and window; a token, when one is sent, must be
# the box's.
UNVERIFIED_CALL_REPORT_SECONDS = 3600
_UNVERIFIED_CALLS_REPORTED: dict[tuple[str, int, str], float] = {}

# What a box and its peripherals are in the registry: pushed to, and admitted
# by the token the box was paired with (`_is_inbound_request_authentic`), which
# the box record holds itself rather than as a registry credential.
REGISTRY_DEFAULTS = {
    "link_mode": "push",
    "auth_type": "none",
    "credential_id": False,
}


class IotBox(models.Model):
    _name = "iot.box"
    _description = "IoT Box"
    _inherits = {"device.device": "device_id"}
    # Who may open a box to remote debugging is its verb's row
    # (security/ir_access.xml), checked where the request leaves for the box.
    _access_verbs = {"remote_debug": models.Verb(requires="read")}

    device_id = fields.Many2one(
        comodel_name="device.device",
        required=True,
        ondelete="cascade",
        help="The registry entry for this box. A box is a device like any "
        "other: it is what custody, maintenance and its peripherals hang on.",
    )

    @api.model
    def _receiver_for_handlers(self, **path_args) -> Self:
        identifier = request.get_http_params().get("identifier")
        if not identifier:
            return self.browse()
        box = self.sudo().search([("identifier", "=", identifier)], limit=1)
        if not box:
            self._refuse_unknown_box_presenting_a_token(identifier)
        return box

    IOT_LOG_ELEMENT_SEPARATOR = b"<log/>\n"
    IOT_LOG_IDENTIFIER_PREFIX = b"identifier "

    @api.model
    def _receiver_for_logs(self, **path_args) -> tuple:
        data = request.httprequest.get_data(cache=True)
        data = data.removesuffix(self.IOT_LOG_ELEMENT_SEPARATOR)
        elements = data.split(self.IOT_LOG_ELEMENT_SEPARATOR)
        if len(elements) < 2 or not elements[0].startswith(
            self.IOT_LOG_IDENTIFIER_PREFIX
        ):
            raise Acknowledged
        identifier = elements[0][len(self.IOT_LOG_IDENTIFIER_PREFIX) :]
        box = self.sudo().search(
            [("identifier", "=", identifier.decode(errors="replace"))], limit=1
        )
        if not box:
            self._refuse_unknown_box_presenting_a_token(
                identifier.decode(errors="replace")
            )
            request.env["integration.exchange"]._record_unknown_caller(
                "iot.box",
                identifier.decode(errors="replace")[:64],
                request.httprequest.remote_addr,
                user_agent=request.httprequest.headers.get("User-Agent"),
                status_code=200,
            )
            raise Acknowledged
        return box, {"log_elements": elements[1:], "purpose": "logs"}

    @api.model
    def _refuse_unknown_box_presenting_a_token(self, identifier: str) -> None:
        """An unknown box that presents a token is answered as a known box
        presenting the wrong one, so the answer does not say which exists."""
        if "Authorization" not in request.httprequest.headers:
            return
        request.env["integration.exchange"]._record_unknown_caller(
            "iot.box",
            identifier[:64],
            request.httprequest.remote_addr,
            user_agent=request.httprequest.headers.get("User-Agent"),
            status_code=401,
        )
        raise Refused(
            401, "unauthenticated request", "authentication_failed", commit=True
        )

    @api.model
    def _prepare_box_refusal_response(self, refused: Refused):
        """A refusal names its code only: the gate's reason names the box,
        which an unknown identifier must not tell apart from a known one."""
        return request.prepare_json_response(
            {"error": refused.error_code}, status=refused.status
        )

    def _note_unverified_call(self, route: str) -> None:
        self.check_singleton()
        key = (self.env.cr.dbname, self.id, route)
        now = time.monotonic()
        reported = _UNVERIFIED_CALLS_REPORTED.get(key)
        if reported is not None and now - reported < UNVERIFIED_CALL_REPORT_SECONDS:
            return
        _UNVERIFIED_CALLS_REPORTED[key] = now
        _logger.warning(
            "IoT box %s called %s without its paired token; heard, as an "
            "upstream iot_drivers sends none there",
            self.identifier,
            route,
        )

    def _inbound_gate_owner(self):
        purpose = "handlers"
        if request and request.httprequest.path == "/iot/log":
            purpose = "logs"
        label = (
            self.env._("%(box)s logs", box=self.name)
            if purpose == "logs"
            else self.env._("%(box)s handler downloads", box=self.name)
        )
        return self, label, purpose

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        self.check_singleton()
        return is_bearer_token_valid(headers, self.token)

    device_ids = fields.One2many(
        comodel_name="iot.device",
        inverse_name="iot_id",
        string="Devices",
    )
    device_count = fields.Count(count_of="device_ids")
    ip = fields.Char(
        related="device_id.endpoint",
        string="Domain Address",
        readonly=False,
    )
    drivers_auto_update = fields.Boolean(
        string="Automatic drivers update",
        default=True,
        help="Automatically update drivers when the IoT Box boots",
    )
    version = fields.Char(
        string="Image Version",
        readonly=True,
    )
    version_commit_url = fields.Html(
        compute="_compute_version_commit_url",
        readonly=True,
    )
    ssl_certificate_end_date = fields.Datetime(
        string="SSL Certificate End Date",
        readonly=True,
    )
    must_install_fdm_module = fields.Boolean(
        string="A fiscal data module is connected to this IoT Box",
        compute="_compute_must_install_fdm_module",
        readonly=True,
    )

    def _default_token(self):
        """Generate a token used in the iot box "token" field or by the wizards used to connect a new IoT Box.
        Also clears the token from the configuration parameters if used to assign the "token" field to
        make the token unique per IoT Box.

        :return: The token generated by the wizard.
        """
        iot_token_value = self._get_pairing_token()
        if not iot_token_value:
            _logger.info(
                "No valid token found in the configuration parameters, generating a new one."
            )
            iot_token_value = secrets.token_hex(16)
            self.env["ir.config_parameter"].sudo().set_param(
                "iot.iot_token", iot_token_value
            )
        return iot_token_value

    @api.model
    def _get_pairing_token(self):
        iot_token_param = (
            self.env["ir.config_parameter"]
            .sudo()
            .search([("key", "=", "iot.iot_token")], limit=1)
        )
        if (
            not iot_token_param.value
            or iot_token_param.write_date + IOT_TOKEN_VALIDITY < fields.Datetime.now()
        ):
            return False
        return iot_token_param.value

    @api.model
    def _spend_pairing_token(self) -> None:
        """The box that used the pairing token spent it: the next box needs
        a new one."""
        self.env["ir.config_parameter"].sudo().set_param("iot.iot_token", "")

    token = fields.Char(
        default=lambda self: self._default_token(),
        readonly=True,
        classification="secret.credential",
        groups="base.group_system",
    )
    # who last sent this box a request upstream boxes answer without a route
    unrouted_reply_keys = fields.Json(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        kind = self.env.ref("iot.kind_iot_box", raise_if_not_found=False)
        for vals in vals_list:
            for field_name, default in REGISTRY_DEFAULTS.items():
                vals.setdefault(field_name, default)
            if kind and not vals.get("device_category_id"):
                vals["device_category_id"] = kind.id
        return super().create(vals_list)

    def unlink(self):
        # The registry row is this box, not a row about it: it goes when the
        # box goes, and takes its peripherals' rows with it by cascade.
        registry_rows = self.device_id
        result = super().unlink()
        registry_rows.unlink()
        return result

    @api.ondelete(at_uninstall=True)
    def _unlink_iot_box(self) -> None:
        self.env["iot.channel"]._send_message(
            {"iot_identifiers": self.mapped("identifier")}, "server_clear"
        )

    def open_homepage(self) -> dict:
        self.check_singleton()
        scheme = urlsplit(request.httprequest.referrer).scheme
        return {
            "type": "ir.actions.act_url",
            "url": f"{scheme}://{self.ip}"
            if scheme == "https"
            else f"{scheme}://{self.ip}:8069",
            "target": "new",
        }

    @api.model
    def connect_iot_box(self, local_iot_boxes):
        """
        This method is called when pressing the "Connect" button in the IoT app.
        Used to connect a new IoT Box to a database.
        :return: action to open the wizard view depending on the result of the iot-proxy request sent by the wizard
        """
        wizard = self.env["wizard.iot.box.pair"].create({})
        self.env["wizard.iot.box.pair.option"].create(
            [
                {
                    "pairing_code": box["pairing_code"],
                    "serial_number": box.get("serial_number"),
                    "add_iot_box_wizard_id": wizard.id,
                }
                for box in local_iot_boxes
            ]
        )
        return wizard.add_iot_box_wizard_action()

    @api.model
    def _get_fdm_module(self) -> str:
        """Module that drives a fiscal data module for the current company.

        The name is answered here rather than by the module itself, because the
        whole point of the prompt is to name a module nobody has installed yet,
        so that module's own code cannot run. A localisation overrides this to
        claim the device for its own country.
        """
        return "pos_blackbox_be" if self.env.company.country_id.code == "BE" else ""

    @api.depends("device_ids")
    def _compute_must_install_fdm_module(self) -> None:
        module_name = self._get_fdm_module()
        installed = bool(module_name) and (
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", module_name)], limit=1)
            .state
            == "installed"
        )
        for box in self:
            box.must_install_fdm_module = (
                bool(module_name)
                and not installed
                and any(
                    device.type == "fiscal_data_module" for device in box.device_ids
                )
            )

    def install_fdm_module(self) -> dict | None:
        """Install the module that drives the connected fiscal data module."""
        if not self.must_install_fdm_module:
            return None

        module_name = self._get_fdm_module()
        module = (
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", module_name)], limit=1)
        )
        if module and module.state != "installed":
            module.button_immediate_install()
            _logger.info("%s installed successfully.", module_name)
            return {
                "type": "ir.actions.client",
                "tag": "reload",
            }
        _logger.warning("%s is already installed or not found.", module_name)
        return None

    @api.depends("version")
    def _compute_version_commit_url(self) -> None:
        base_url = "https://www.github.com/odoo/odoo/commit/"
        for box in self:
            if box.version and "#" in box.version:
                image_version, commit_hash = box.version.split("#", 1)
                box.version_commit_url = f'<span>{image_version}#<a href="{base_url}{commit_hash}" target="_blank">{commit_hash}</a></span>'
            else:
                box.version_commit_url = (
                    f"<span>{box.version}</span>" if box.version else False
                )
