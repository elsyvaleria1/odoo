from typing import Any

from odoo import fields, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardResUsersUpdatePassword(models.TransientModel):
    _name = "wizard.res.users.update.password"
    _description = "Change Password Wizard"
    _transient_max_hours = 0.2

    def _default_user_ids(self) -> list[tuple[int, int, dict[str, Any]]]:
        user_ids = (
            self.env.context.get("active_model") == "res.users"
            and self.env.context.get("active_ids")
        ) or []
        return [
            Command.create({"user_id": user.id, "user_login": user.login})
            for user in self.env["res.users"].browse(user_ids)
        ]

    user_ids = fields.One2many(
        comodel_name="wizard.res.users.update.password.line",
        inverse_name="wizard_id",
        string="Users",
        default=lambda self: self._default_user_ids(),
    )

    def change_password_button(self) -> dict[str, str]:
        self.check_singleton()
        self.user_ids.change_password_button()
        if self.env.user in self.user_ids.user_id:
            return {"type": "ir.actions.client", "tag": "reload"}
        return {"type": "ir.actions.act_window_close"}
