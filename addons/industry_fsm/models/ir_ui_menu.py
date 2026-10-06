from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self):
        res = super()._get_blacklisted_menu_ids()
        if not self.env.user.has_group("industry_fsm.group_fsm_manager"):
            res.append(
                self.env.ref("industry_fsm.fsm_menu_reporting_customer_ratings").id
            )
        return res
