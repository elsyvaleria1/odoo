from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardResUsersUpdatePasswordLine(models.TransientModel):
    _name = "wizard.res.users.update.password.line"
    _description = "User, Change Password Wizard"
    wizard_id = fields.Many2one(
        comodel_name="wizard.res.users.update.password",
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        ondelete="cascade",
    )
    user_login = fields.Char(readonly=True)
    new_passwd = fields.Char(
        string="New Password",
        default="",
    )

    def change_password_button(self) -> None:
        _debug.lifecycle(
            "wizard_change_password",
            by=self.env.uid,
            users=[line.user_id.id for line in self if line.new_passwd],
        )
        for line in self:
            if line.new_passwd:
                line.user_id._change_password(line.new_passwd)
        self.write({"new_passwd": False})
