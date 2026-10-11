import base64
import logging

from odoo import Command, fields, models
from odoo.http import request
from odoo.tools import SQL

from .._vendor.webauthn.helpers import bytes_to_base64url
from odoo.addons.base.models.res_users import check_identity

_logger = logging.getLogger(__name__)


class WizardAuthPasskeyKeyCreate(models.TransientModel):
    _name = "wizard.auth.passkey.key.create"
    _description = "Create a Passkey"

    name = fields.Char(required=True)

    @check_identity
    def action_generate_key(self, registration=None):
        assert registration, "registration can not be empty"
        self.check_singleton()
        verification = request.env["auth.passkey.key"]._get_registration_credential(
            registration
        )
        self.env.user.write(
            {
                "auth_passkey_key_ids": [
                    Command.create(
                        {
                            "name": self.name,
                            "credential_identifier": bytes_to_base64url(
                                verification["credential_id"]
                            ),
                        }
                    )
                ]
            }
        )
        passkey = self.env.user.auth_passkey_key_ids[0]
        self.env.cr.execute(
            SQL(
                "UPDATE auth_passkey_key SET public_key = %s WHERE id = %s",
                base64.urlsafe_b64encode(
                    verification["credential_public_key"]
                ).decode(),
                passkey.id,
            )
        )
        ip = request.httprequest.remote_addr if request else "n/a"
        _logger.info(
            "Passkey (#%d) created by %s (#%d) from %s",
            passkey.id,
            self.env.user.login,
            self.env.user.id,
            ip,
        )
        new_token = self.env.user._get_session_token(request.session.sid)
        request.session.session_token = new_token
        return True
