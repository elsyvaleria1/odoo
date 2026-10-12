import logging

import requests

from odoo import fields, models

_logger = logging.getLogger(__name__)


class WizardIotBoxPair(models.TransientModel):
    _name = "wizard.iot.box.pair"
    _description = "Add IoT Box wizard"

    stage = fields.Selection(
        selection=[
            ("start", "Start"),
            ("connect", "Connect"),
            ("manual", "Manual"),
            ("pair_offline", "Offline Pairing"),
        ],
        default="start",
    )

    discovered_box_ids = fields.One2many(
        comodel_name="wizard.iot.box.pair.option",
        inverse_name="add_iot_box_wizard_id",
    )
    iot_box_to_connect = fields.Many2one(comodel_name="wizard.iot.box.pair.option")
    serial_number = fields.Char()
    pairing_code = fields.Char()

    offline_pairing_token = fields.Char(
        string="Token",
        default=lambda self: self._default_offline_pairing_token(),
        store=False,
        readonly=True,
    )

    def _connect_iot_box_with_pairing_code(self):
        if self.iot_box_to_connect:
            self.pairing_code = self.iot_box_to_connect.pairing_code
            self.serial_number = self.iot_box_to_connect.serial_number
        try:
            icp_sudo = self.env["ir.config_parameter"].sudo()
            response = self.env["ir.egress"].request(
                "POST",
                "https://iot-proxy.odoo.com/odoo-enterprise/iot/connect-db",
                purpose="iot_pairing",
                json={
                    "params": {
                        "pairing_code": self.pairing_code,
                        "database_url": self.get_base_url(),
                        "token": self.env["iot.box"]._default_token(),
                        "db_uuid": icp_sudo.get_param("database.uuid"),
                        "enterprise_code": icp_sudo.get_param(
                            "database.enterprise_code"
                        ),
                    },
                },
                timeout=5,
            )

            response.raise_for_status()
            json = response.json()

            error = json.get("error")
            if error:
                _logger.warning(
                    "Error when using pairing code %s. IoT Proxy responded with an error message: %s",
                    self.pairing_code,
                    error,
                )
                return self._open_no_iot_box_found_action()
            result = json.get("result")
            if result and result[0]:
                return self._open_connecting_action()
            else:
                _logger.warning(
                    "Failed to connect the IoT Box with pairing code %s: %s",
                    self.pairing_code,
                    json,
                )
        except requests.exceptions.RequestException, ValueError:
            _logger.exception(
                "Failed to use the provided pairing code %s to connect an iot box",
                self.pairing_code,
            )
        return self._open_no_iot_box_found_action()

    def _open_select_box_to_connect_action(self) -> dict:
        self.stage = "connect"
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.iot.box.pair",
            "res_id": self.id,
            "name": self.env._("Several IoT's detected"),
            "views": [[self.env.ref("iot.view_select_box_to_connect").id, "form"]],
            "target": "new",
        }

    def _open_enter_pairing_code_action(self) -> dict:
        self.stage = "connect"
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.iot.box.pair",
            "res_id": self.id,
            "name": self.env._("Searching for an IoT Box..."),
            "views": [[self.env.ref("iot.view_enter_pairing_code").id, "form"]],
            "target": "new",
        }

    def _open_no_iot_box_found_action(self) -> dict:
        self.stage = "manual"
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.iot.box.pair",
            "res_id": self.id,
            "name": self.env._("Searching for an IoT Box..."),
            "views": [[self.env.ref("iot.view_no_iot_box_found").id, "form"]],
            "target": "new",
            "no_iot_found_found": True,
        }

    def _open_connecting_action(self) -> dict:
        if self.serial_number:
            name = self.env._("IoT Box %s found. Connecting...", self.serial_number)
        else:
            name = self.env._("IoT Box found. Connecting...")

        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.iot.box.pair",
            "res_id": self.id,
            "name": name,
            "views": [[self.env.ref("iot.view_add_iot_box").id, "form"]],
            "target": "new",
        }

    def open_documentation_url(self) -> dict:
        return {
            "type": "ir.actions.act_url",
            "url": "https://www.odoo.com/documentation/latest/applications/general/iot/iot_box.html",
            "target": "new",
        }

    def _start_stage(self):
        n_detected_iot_boxes = len(self.discovered_box_ids)

        if n_detected_iot_boxes > 1:
            return self._open_select_box_to_connect_action()
        elif n_detected_iot_boxes == 1:
            self.pairing_code = self.discovered_box_ids[0].pairing_code
            self.serial_number = self.discovered_box_ids[0].serial_number
            return self._connect_iot_box_with_pairing_code()
        else:
            return self._open_no_iot_box_found_action()

    def add_iot_box_wizard_action(self):
        match self.stage:
            case "start":
                return self._start_stage()
            case "manual":
                return self._open_enter_pairing_code_action()
            case "connect":
                return self._connect_iot_box_with_pairing_code()
        return None

    def pair_offline(self):
        if self.stage == "pair_offline":
            self.stage = "start"
            return self._start_stage()

        self.stage = "pair_offline"
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.iot.box.pair",
            "res_id": self.id,
            "name": self.env._("Pair an IoT Box offline"),
            "views": [[self.env.ref("iot.view_pair_offline").id, "form"]],
            "target": "new",
        }

    def _default_offline_pairing_token(self) -> str:
        icp_sudo = self.env["ir.config_parameter"].sudo()
        token = self.env["iot.box"]._default_token()
        url = self.get_base_url()
        db_uuid = icp_sudo.get_param("database.uuid", default="")
        db_name = self.env.cr.dbname
        enterprise_code = icp_sudo.get_param("database.enterprise_code", default="")

        return f"{url}?token={token}&db_uuid={db_uuid}&enterprise_code={enterprise_code}&db_name={db_name}"
