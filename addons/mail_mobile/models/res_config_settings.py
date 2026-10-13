import logging as logger
import uuid

import odoo
from odoo import api, fields, models
from odoo.tools import iap

_logger = logger.getLogger(__name__)

DEFAULT_ENDPOINT = "https://ocn.odoo.com"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    enable_ocn = fields.Boolean(
        string="Push Notifications",
        config_parameter="mail_mobile.enable_ocn",
    )

    def _get_endpoint(self):
        return self.env.registry.settings.get(
            self.env, "odoo_ocn.endpoint", DEFAULT_ENDPOINT
        )

    @api.model
    def get_fcm_project_id(self):
        ir_params_sudo = self.env["ir.config_parameter"].sudo()
        if not ir_params_sudo.get_param_bool("mail_mobile.enable_ocn"):
            return None
        project_id = ir_params_sudo.get_param("odoo_ocn.project_id")
        if not project_id:
            params = {
                "ocnuuid": self._get_ocn_uuid(),
                "server_version": odoo.release.version,
                "db": self.env.cr.dbname,
                "company_name": self.env.company.name,
                "url": ir_params_sudo.get_param("web.base.url"),
            }
            try:
                project_id = iap.jsonrpc(
                    self._get_endpoint() + "/iap/ocn/enable_service",
                    params=params,
                    env=self.env,
                )
                ir_params_sudo.set_param("odoo_ocn.project_id", project_id)
            except Exception:
                _logger.exception("An error occurred while contacting the ocn server")
        return project_id

    @api.model
    def _get_ocn_uuid(self):
        push_uuid = self.env.registry.settings.get(self.env, "ocn.uuid", False)
        if not push_uuid:
            push_uuid = str(uuid.uuid4())
            self.env["ir.config_parameter"].sudo().set_param("ocn.uuid", push_uuid)
        return push_uuid

    @api.model
    def register_device(self, fcm_token, device_name, fcm_token_old=None):
        values = {
            "ocn_uuid": self._get_ocn_uuid(),
            "user_name": self.env.user.name or self.env.user.login,
            "user_login": self.env.user.login,
            "device_name": device_name,
            "device_key": fcm_token,
            "fcm_token_old": fcm_token_old,
        }
        result = False
        try:
            result = iap.jsonrpc(
                self._get_endpoint() + "/iap/ocn/register_device",
                params=values,
                env=self.env,
            )
        except Exception:
            _logger.exception("An error occurred while contacting the ocn server")

        if result:
            self.env.user.partner_id.ocn_token = result
            return result
        return False
