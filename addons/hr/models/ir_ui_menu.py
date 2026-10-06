from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self):
        res = super()._get_blacklisted_menu_ids()
        if not self.env.user.has_group("hr.group_hr_user"):
            is_department_manager = bool(
                self.env["hr.department"].search_count(
                    [("manager_id", "in", self.env.user.employee_ids.ids)], limit=1
                )
            )
            _debug.logic(
                "non_hr_user_blacklist",
                uid=self.env.uid,
                department_manager=is_department_manager,
            )
            if not is_department_manager and (
                dep_menu := self.env.ref(
                    "hr.menu_hr_department_kanban", raise_if_not_found=False
                )
            ):
                res.append(dep_menu.id)
        return res
