from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from ..models.res_users import check_identity

_debug = DebugLog(__name__)


class WizardResUsersUpdatePasswordOwn(models.TransientModel):
    _name = "wizard.res.users.update.password.own"
    _description = "User, change own password wizard"
    _transient_max_hours = 0.1

    new_password = fields.Char()
    confirm_password = fields.Char(string="New Password (Confirmation)")

    @api.constrains("new_password", "confirm_password")
    def _check_password_confirmation(self) -> None:
        for record in self:
            if record.confirm_password != record.new_password:
                raise ValidationError(
                    self.env._(
                        "The new password and its confirmation must be identical."
                    )
                )

    @check_identity
    def change_password(self) -> dict[str, str]:
        self.env.user._change_password(self.new_password or "")
        self.unlink()
        return {"type": "ir.actions.client", "tag": "reload"}
