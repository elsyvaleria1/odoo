from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self) -> list:
        res = super()._get_blacklisted_menu_ids()
        if not self.env.user.has_group("project.group_project_manager") and (
            menu := self.env.ref(
                "project.menu_project_customer_ratings", raise_if_not_found=False
            )
        ):
            res.append(menu.id)
        if self.env.user.has_group("project.group_project_stages"):
            for xmlid in [
                "project.menu_projects",
                "project.menu_projects_config",
            ]:
                if menu := self.env.ref(xmlid, raise_if_not_found=False):
                    res.append(menu.id)
        _debug.logic(
            "menus_blacklisted",
            user=self.env.uid,
            manager=self.env.user.has_group("project.group_project_manager"),
            stages=self.env.user.has_group("project.group_project_stages"),
            menus=res,
        )
        return res
